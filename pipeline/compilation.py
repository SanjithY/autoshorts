""""Top 5 <streamer> moments": most-viewed recent clips of an allowlisted streamer, counted down.

Only streamers listed in config.yaml with permission: true are ever used (reposting
other people's streams without permission gets copyright strikes).
"""
from __future__ import annotations

import datetime as dt
import random
import subprocess
import tempfile
from pathlib import Path

import requests

from . import clips
from .render.scenes import render_animated

HELIX = "https://api.twitch.tv/helix"


def top_clips(cfg, streamer: dict, n=5, used_ids=()):
    hdr = clips._twitch_headers()
    if not hdr:
        return []
    u = requests.get(f"{HELIX}/users", headers=hdr, params={"login": streamer["login"]}, timeout=20).json()
    if not u.get("data"):
        return []
    days = int(cfg.get("compilation", {}).get("lookback_days", 7))
    since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat() + "Z"
    data = requests.get(f"{HELIX}/clips", headers=hdr, params={
        "broadcaster_id": u["data"][0]["id"], "started_at": since, "first": 50}, timeout=20).json().get("data", [])
    data = [c for c in data if c["id"] not in used_ids and 6 <= c["duration"] <= 60]
    data.sort(key=lambda c: c["view_count"], reverse=True)
    return data[:n]


def concat(parts, out):
    lst = Path(tempfile.mkdtemp()) / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", "fps=30,scale=1080:1920,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "20", "-af", "aresample=44100,loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac",
                    "-b:a", "192k", "-movflags", "+faststart", out], check=True)


def build(cfg, out_path, state, prefer=None):
    streamers = clips.allowed_streamers(cfg)
    if not streamers:
        return None
    random.shuffle(streamers)
    if prefer:  # a queued script can ask for a specific streamer first
        streamers.sort(key=lambda s: s["login"].lower() != str(prefer).lower())
    for st in streamers:
        cl = top_clips(cfg, st, int(cfg.get("compilation", {}).get("count", 5)), set(state.get("used_clip_ids", [])))
        if len(cl) < 3:
            continue
        name = cl[0]["broadcaster_name"]
        tmp = Path(tempfile.mkdtemp())
        parts = []
        intro = {"kicker": f"{name} · top {len(cl)}", "theme": "gaming", "scenes": [
            {"type": "hook", "text": f"Top {len(cl)} {name} moments", "highlight": [name],
             "say": f"The top {len(cl)} {name} moments this week. Number one is crazy."}]}
        render_animated(intro, str(tmp / "intro.mp4"), cfg, seed=1)
        parts.append(tmp / "intro.mp4")
        per = max(8.0, 52.0 / len(cl))
        for rank, c in zip(range(len(cl), 0, -1), reversed(cl)):  # count down 5 -> 1
            src = clips.download_clip(c, tmp)
            words = clips.transcribe_words(src)
            start = max(0.0, c["duration"] - per)  # the payoff is usually at the end of a clip
            seg = tmp / f"clip{rank}.mp4"
            clips.render_clip(src, c["title"][:60], f"twitch.tv/{c['broadcaster_name']}", str(seg),
                              words, badge=f"#{rank}", start=start, max_len=per)
            parts.append(seg)
        concat([str(p) for p in parts], out_path)
        return {"format": "top5_streamer", "title": f"Top {len(cl)} {name} moments this week #shorts",
                "description": "Clips used with permission. " + " | ".join(f"#{len(cl)-i}: {c['url']}" for i, c in enumerate(reversed(cl))),
                "hashtags": [f"#{name.lower()}", "#twitch", "#clips", "#shorts"],
                "clip_ids": [c["id"] for c in cl]}
    return None
