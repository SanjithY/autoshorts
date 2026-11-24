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
from .render.moments import render_card, render_moment

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


def hook_title(name, top):
    """A curiosity title built from the #1 clip, instead of a generic 'Top N moments'."""
    import re
    t = re.sub(r"\s+", " ", re.sub(r"[^\x20-\x7E]", "", top.get("title", ""))).strip(" -|:!.")
    words = t.split()
    if 3 <= len(words) <= 9 and len(t) <= 48 and not re.search(r"(https?://|#|@)", t):
        return f"{name}: {t} 😭 #shorts"
    hooks = [f"{name} did NOT expect this 😭 #shorts", f"{name}'s stream got out of hand this week 😭 #shorts",
             f"Wait for {name}'s #1 moment 😭 #shorts", f"{name} had the craziest week on stream 😂 #shorts"]
    return hooks[sum(map(ord, top.get("id", ""))) % len(hooks)]


def concat(parts, out):
    lst = Path(tempfile.mkdtemp()) / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", "fps=30,scale=1080:1920:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "fast",
                    "-crf", "19", "-af", "aresample=44100,loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac",
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
        n = len(cl)
        order = list(zip(range(n, 0, -1), reversed(cl)))  # count down: #n ... #1
        srcs = {c["id"]: clips.download_clip(c, tmp) for c in cl}
        # no intro card: the video opens straight on clip #n with the title laid over it
        per = max(8.0, float(cfg.get("compilation", {}).get("target_seconds", 30)) / n)
        for idx, (rank, c) in enumerate(order):
            src = srcs[c["id"]]
            words = clips.transcribe_words(src)
            start = max(0.0, c["duration"] - per)  # the payoff is usually at the end of a clip
            seg = tmp / f"clip{rank}.mp4"
            render_moment(src, str(seg), title=c["title"], streamer=name, credit=f"twitch.tv/{c['broadcaster_name']}",
                          rank=rank, total=n, words=words, start=start, max_len=per, seg_index=idx,
                          hook={"big": f"TOP {n}", "pill": name.upper(), "small": "MOMENTS THIS WEEK"} if idx == 0 else None)
            parts.append(seg)
        render_card(srcs[cl[0]["id"]], str(tmp / "outro.mp4"), big="WHICH ONE?", pill="WAS YOUR #1",
                    small="TELL ME IN THE COMMENTS", say="Which one was your number one? Tell me in the comments.",
                    outro=True)
        parts.append(tmp / "outro.mp4")
        concat([str(p) for p in parts], out_path)
        return {"format": "top5_streamer", "title": hook_title(name, cl[0]),
                "description": "Clips used with permission. " + " | ".join(f"#{len(cl)-i}: {c['url']}" for i, c in enumerate(reversed(cl))),
                "hashtags": [f"#{name.lower()}", "#twitch", "#clips", "#shorts"],
                "clip_ids": [c["id"] for c in cl]}
    return None
