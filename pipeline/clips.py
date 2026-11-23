"""Clip sourcing (allowlisted Twitch streamers only) and the clip_react renderer."""
from __future__ import annotations

import datetime as dt
import math
import os
import random
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import requests
from PIL import Image

from .render.core import (BLACK, FPS, H, W, WHITE, YELLOW, Encoder, caption_chunks, draw_caption,
                          draw_progress, ease_out_back, paste, rounded_box, text_sprite)

HELIX = "https://api.twitch.tv/helix"


def _twitch_headers():
    cid = (os.environ.get("TWITCH_CLIENT_ID") or "").strip()
    sec = (os.environ.get("TWITCH_CLIENT_SECRET") or "").strip()
    if not (cid and sec):
        print("[twitch] TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET not set")
        return None
    tok = requests.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": cid, "client_secret": sec, "grant_type": "client_credentials"}, timeout=20).json()
    if "access_token" not in tok:
        # shows Twitch's reason only (e.g. "invalid client secret"), never the keys
        print(f"[twitch] login failed: {tok.get('message', tok)} (client id length {len(cid)}, secret length {len(sec)})")
        return None
    return {"Client-Id": cid, "Authorization": f"Bearer {tok['access_token']}"}


def allowed_streamers(cfg):
    return [s for s in (cfg.get("twitch_clips", {}).get("streamers") or []) if s.get("permission") is True]


def find_clip(cfg, used_ids: set):
    tc = cfg.get("twitch_clips", {})
    streamers = allowed_streamers(cfg)
    hdr = _twitch_headers() if streamers else None
    if not hdr:
        return None
    game = requests.get(f"{HELIX}/games", headers=hdr, params={"name": tc.get("game_name", "")}, timeout=20).json()
    game_id = game["data"][0]["id"] if game.get("data") else None
    since = (dt.datetime.utcnow() - dt.timedelta(hours=tc.get("lookback_hours", 48))).isoformat() + "Z"
    pool = []
    for s in streamers:
        u = requests.get(f"{HELIX}/users", headers=hdr, params={"login": s["login"]}, timeout=20).json()
        if not u.get("data"):
            continue
        clips = requests.get(f"{HELIX}/clips", headers=hdr, params={
            "broadcaster_id": u["data"][0]["id"], "started_at": since, "first": 20}, timeout=20).json()
        for c in clips.get("data", []):
            if c["id"] in used_ids or c["view_count"] < tc.get("min_views", 0):
                continue
            if game_id and c.get("game_id") != game_id:
                continue
            if 8 <= c["duration"] <= 60:
                pool.append(c)
    pool.sort(key=lambda c: c["view_count"], reverse=True)
    return pool[0] if pool else None


def download_clip(clip, out_dir):
    out = str(Path(out_dir) / f"{clip['id']}.mp4")
    subprocess.run(["yt-dlp", "-q", "-f", "best[ext=mp4]/best", "-o", out, clip["url"]], check=True)
    return out


def transcribe_words(path):
    from faster_whisper import WhisperModel
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "base.en"), compute_type="int8")
    segs, _ = model.transcribe(path, word_timestamps=True, vad_filter=True)
    words = []
    for s in segs:
        for w in s.words or []:
            words.append({"w": w.word.strip(), "start": w.start, "end": w.end})
    return words


def render_clip(video_path, hook, credit, out_path, words=None, badge=None, start=0.0, max_len=None):
    """Blurred-fill 9:16 frame, original clip centered, hook title on top, captions, credit tag."""
    tmp = Path(tempfile.mkdtemp())
    wav = str(tmp / "a.wav")
    full = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "default=nw=1:nk=1", video_path]))
    dur = min(full - start, max_len) if max_len else full - start
    cut = ["-ss", str(start), "-t", str(dur)]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *cut, "-i", video_path, "-vn", "-ac", "2", "-ar", "44100", wav], check=True)
    if words:
        words = [{**w, "start": w["start"] - start, "end": w["end"] - start} for w in words
                 if start <= w["start"] < start + dur]
    vf = (f"[0:v]fps={FPS},split[a][b];"
          f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,eq=brightness=-0.15[bg];"
          f"[b]scale={W}:-2[fg];[bg][fg]overlay=0:(H-h)/2-40,format=rgb24")
    dec = subprocess.Popen(["ffmpeg", "-v", "error", *cut, "-i", video_path, "-filter_complex", vf, "-an",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = Encoder(out_path, wav)
    chunks = caption_chunks(words or [])
    hook_spr = text_sprite(hook.upper(), "display", 112, WHITE, 10, BLACK, 960, True, 0.02, (), YELLOW)
    cred = text_sprite(credit, "bold", 36, WHITE, 0, BLACK, 800, False)
    cred_box = rounded_box(cred.width + 40, cred.height + 16, (0, 0, 0, 170), 20)
    cred_box.paste(cred, (20, 8), cred)
    badge_spr = None
    if badge:
        bt = text_sprite(badge, "display", 130, YELLOW, 10, BLACK, 300)
        badge_spr = bt
    fi = 0
    while True:
        buf = dec.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        t = fi / FPS
        frame = Image.fromarray(np.frombuffer(buf, np.uint8).reshape(H, W, 3)).copy()
        paste(frame, hook_spr, W / 2, 330, 0.6 + 0.4 * ease_out_back(t / 0.3))
        if badge:
            paste(frame, badge_spr, W / 2, 530, 1 + 0.08 * math.sin(t * 5))
        paste(frame, cred_box, W / 2, 1180, 1)
        draw_caption(frame, chunks, t, y=1380)
        draw_progress(frame, t, dur)
        enc.write(frame)
        fi += 1
    enc.close()
    return {"duration": dur, "path": out_path}


def pick_footage(cfg):
    d = Path(cfg.get("footage_dir", "footage"))
    vids = [p for p in d.glob("*") if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm")] if d.exists() else []
    if not vids:
        return None, 0.0
    v = random.choice(vids)
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "default=nw=1:nk=1", str(v)]))
    return str(v), random.uniform(0, max(0.0, dur - 45))
