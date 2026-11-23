"""Topic-matched backgrounds.

Priority for each scene:
  1. Real footage from the tagged library (footage/<topic>/*.mp4 or the repo's "footage" release),
     matched to what the scene talks about (file names are the tags: police_chase.mp4).
  2. Optional free stock video from Pexels by keyword (PEXELS_API_KEY secret).
  3. A themed animated backdrop: news (VHS tape + breaking banner), gaming, sports, tech, money, space,
     entertainment.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import subprocess
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

from .core import (BLACK, FPS, H, HOT, NIGHT, ORANGE, PINK, PURPLE, TEAL, W, WHITE, YELLOW,
                   SynthwaveBackground, VideoBackground, font, text_sprite, paste)

ROOT = Path(__file__).resolve().parents[2]
FOOTAGE = ROOT / "footage"
STOP = set("the a an and or of to in on for with is are was it this that you your my we they he she be".split())


def _tokens(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP and len(w) > 2}


def library(topic: str | None = None):
    vids = []
    if FOOTAGE.exists():
        for p in FOOTAGE.rglob("*"):
            if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm"):
                rel = p.relative_to(FOOTAGE)
                folder = rel.parts[0].lower() if len(rel.parts) > 1 else ""
                name = p.stem.lower()
                ptopic = folder or (name.split("__")[0] if "__" in name else "")
                tags = _tokens(name.replace("__", " ").replace("_", " ").replace("-", " "))
                vids.append({"path": str(p), "topic": ptopic, "tags": tags})
    if topic:
        t = re.sub(r"[^a-z0-9]", "", topic.lower())
        vids = [v for v in vids if re.sub(r"[^a-z0-9]", "", v["topic"]) == t] or []
    return vids


def best_clip(clips, scene_text, used):
    if not clips:
        return None
    words = _tokens(scene_text)
    scored = sorted(clips, key=lambda c: (-len(c["tags"] & words), c["path"] in used, random.random()))
    return scored[0]


def _duration(path):
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                              "-of", "default=nw=1:nk=1", path]))
    except Exception:
        return 0.0


# ---------------------------------------------------------------- Pexels (optional stock B-roll)
def pexels_clip(query: str, cache=ROOT / "footage" / "_stock"):
    key = os.environ.get("PEXELS_API_KEY")
    if not key or not query:
        return None
    cache.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": key}, timeout=20,
                         params={"query": query, "orientation": "portrait", "per_page": 10, "size": "medium"}).json()
        vids = r.get("videos", [])
        if not vids:
            return None
        v = random.choice(vids[:6])
        files = sorted([f for f in v["video_files"] if f.get("height", 0) >= 1280 and f.get("file_type") == "video/mp4"],
                       key=lambda f: f["height"]) or v["video_files"]
        out = cache / f"pexels_{v['id']}.mp4"
        if not out.exists():
            out.write_bytes(requests.get(files[0]["link"], timeout=60).content)
        return str(out)
    except Exception as ex:
        print(f"[bg] pexels failed: {ex}")
        return None


# ---------------------------------------------------------------- themed animated backdrops
class NewsTape:
    """Retro news tape: dark studio gradient, VHS scanlines/noise, REC dot, timestamp, BREAKING banner."""

    def __init__(self, seed=0, footage=None, start=0.0, label="BREAKING NEWS"):
        self.rnd = random.Random(seed)
        self.video = VideoBackground(footage, start, dim=0.25) if footage else None
        y = np.linspace(0, 1, H)[:, None, None]
        base = (np.array((8, 18, 48)) * (1 - y) + np.array((30, 70, 150)) * y)
        self.base = Image.fromarray(np.broadcast_to(base, (H, W, 3)).astype(np.uint8))
        d = ImageDraw.Draw(self.base)
        for i in range(0, W, 90):  # world-map-ish dot grid
            for j in range(250, 1250, 90):
                if (i * 7 + j * 3) % 5:
                    d.ellipse((i, j, i + 8, j + 8), fill=(70, 140, 255))
        scan = np.zeros((H, W), np.uint8)
        scan[::4] = 38
        self.scan = Image.fromarray(scan).convert("L")
        self.label = label
        self.banner = text_sprite(label, "display", 62, WHITE, 0, BLACK, 900, False, 0.0)

    def frame(self, t):
        img = self.video.frame(t) if self.video else self.base.copy()
        # VHS: horizontal jitter band + noise speckles + scanlines
        arr = np.asarray(img).copy()
        band = int((t * 220) % H)
        arr[band:band + 18] = np.roll(arr[band:band + 18], int(8 * math.sin(t * 30)), axis=1)
        noise = np.random.randint(0, 2, (H // 6, W // 6), np.uint8) * 22
        noise = np.kron(noise, np.ones((6, 6), np.uint8))[:H, :W, None]
        arr = np.clip(arr.astype(np.int16) + noise - 11, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
        img.paste((0, 0, 0), (0, 0, W, H), self.scan)
        d = ImageDraw.Draw(img)
        if int(t * 2) % 2 == 0:
            d.ellipse((60, 160, 96, 196), fill=(255, 40, 40))
        d.text((110, 158), "REC", font=font("black", 38), fill=WHITE)
        d.text((W - 360, 158), f"00:{int(t)//60:02d}:{int(t)%60:02d}:{int(t*30)%30:02d}", font=font("bold", 36), fill=WHITE)
        # breaking banner just above the caption zone
        d.rectangle((0, 1180, W, 1262), fill=(200, 16, 40))
        img.paste(self.banner, (40, 1221 - self.banner.height // 2), self.banner)
        d.rectangle((0, 1262, W, 1300), fill=(15, 15, 25))
        tick = "LIVE UPDATES  •  " * 6
        off = int(t * 160) % 600
        d.text((-off, 1266), tick, font=font("bold", 26), fill=YELLOW)
        return img


class Stadium:
    def __init__(self, seed=0):
        y = np.linspace(0, 1, H)[:, None, None]
        base = np.array((10, 20, 40)) * (1 - y) + np.array((20, 90, 50)) * y
        self.base = Image.fromarray(np.broadcast_to(base, (H, W, 3)).astype(np.uint8))
        d = ImageDraw.Draw(self.base)
        for x in (120, 540, 960):
            d.rectangle((x - 70, 180, x + 70, 240), fill=(240, 240, 230))
        for i in range(0, W, 140):
            d.line((i, 1250, i - 300, H), fill=(240, 255, 240), width=6)
        d.rectangle((0, 1240, W, 1250), fill=(240, 255, 240))
        self.glow = Image.new("RGB", (W, H), (255, 255, 220))

    def frame(self, t):
        img = self.base.copy()
        d = ImageDraw.Draw(img)
        rnd = random.Random(int(t * 8))
        for _ in range(40):  # camera flashes in the crowd
            x, y = rnd.randrange(W), rnd.randrange(300, 1000)
            d.ellipse((x, y, x + 5, y + 5), fill=(255, 255, 255))
        return img


class TechGrid:
    def __init__(self, seed=0):
        self.base = Image.new("RGB", (W, H), (6, 12, 24))
        d = ImageDraw.Draw(self.base)
        rnd = random.Random(seed)
        for _ in range(70):  # circuit traces
            x, y = rnd.randrange(W), rnd.randrange(H)
            for _ in range(4):
                nx = x + rnd.choice((-1, 1)) * rnd.randrange(40, 200)
                ny = y + rnd.choice((-1, 1)) * rnd.randrange(40, 200)
                d.line((x, y, nx, y), fill=(0, 90, 120), width=3)
                d.line((nx, y, nx, ny), fill=(0, 90, 120), width=3)
                d.ellipse((nx - 6, ny - 6, nx + 6, ny + 6), outline=(0, 200, 255), width=3)
                x, y = nx, ny

    def frame(self, t):
        img = self.base.copy()
        d = ImageDraw.Draw(img)
        y = int(t * 400) % H
        d.rectangle((0, y, W, y + 3), fill=(0, 229, 255))
        return img


class Starfield:
    def __init__(self, seed=0):
        rnd = np.random.default_rng(seed)
        self.stars = rnd.uniform(-1, 1, (500, 3)) * [1, 1, 0] + [0, 0, 0]
        self.stars[:, 2] = rnd.uniform(0.05, 1, 500)

    def frame(self, t):
        img = Image.new("RGB", (W, H), (4, 4, 16))
        d = ImageDraw.Draw(img)
        for x, y, z in self.stars:
            zz = (z - t * 0.12) % 1 + 0.02
            sx, sy = W / 2 + x / zz * 300, H / 2 + y / zz * 300
            if 0 <= sx < W and 0 <= sy < H:
                r = max(2, int(6 * (1 - zz)))
                d.ellipse((sx - r, sy - r, sx + r, sy + r), fill=(255, 255, 255))
        return img


class MoneyChart:
    def __init__(self, seed=0):
        self.rnd = random.Random(seed)
        self.pts = [700]
        for _ in range(60):
            self.pts.append(max(250, min(1150, self.pts[-1] + self.rnd.uniform(-90, 60))))

    def frame(self, t):
        img = Image.new("RGB", (W, H), (6, 24, 16))
        d = ImageDraw.Draw(img)
        for y in range(200, 1300, 110):
            d.line((0, y, W, y), fill=(20, 60, 40), width=2)
        n = int(4 + (t * 8) % 57)
        xs = [i * W / 60 for i in range(n)]
        pts = list(zip(xs, [300 + (p - 250) * 0.95 for p in self.pts[:n]]))
        if len(pts) > 1:
            d.polygon(pts + [(pts[-1][0], 1300), (0, 1300)], fill=(14, 60, 36))
            d.line(pts, fill=(60, 230, 120), width=10)
            d.ellipse((pts[-1][0] - 14, pts[-1][1] - 14, pts[-1][0] + 14, pts[-1][1] + 14), fill=(160, 255, 190))
        return img


class Spotlight:
    def frame(self, t):
        img = Image.new("RGB", (W, H), (20, 8, 30))
        d = ImageDraw.Draw(img)
        for i, col in enumerate(((255, 64, 160), (0, 200, 255), (255, 200, 60))):
            a = math.sin(t * 0.8 + i * 2) * 0.5
            cx = W / 2 + math.sin(a) * 900
            d.polygon([(W / 2 + (i - 1) * 300, 0), (cx - 220, H), (cx + 220, H)], fill=tuple(c // 4 for c in col))
        rnd = random.Random(int(t * 4))
        for _ in range(3):  # paparazzi camera flashes
            if rnd.random() < 0.5:
                x, y = rnd.randrange(W), rnd.randrange(200, 1200)
                d.ellipse((x - 40, y - 40, x + 40, y + 40), fill=(255, 255, 240))
        return img.filter(ImageFilter.GaussianBlur(6))


THEMES = {"news": NewsTape, "sports": Stadium, "tech": TechGrid, "space": Starfield, "science": Starfield,
          "money": MoneyChart, "finance": MoneyChart, "entertainment": Spotlight, "celebrity": Spotlight,
          "gaming": SynthwaveBackground}


class SceneBackgrounds:
    """Picks a background per scene: matching footage when available, otherwise the theme backdrop."""

    def __init__(self, script: dict, timeline: list, seed: int, cfg: dict):
        self.timeline = timeline
        topic = script.get("topic_key") or cfg.get("focus", {}).get("topic_key")
        theme = script.get("theme", "gaming")
        clips = library(topic)
        used = set()
        self.per_scene = []
        stock_query = script.get("stock_query")
        fixed = script.get("footage")  # a video *about* one specific clip: play it straight through
        if fixed:
            fp = FOOTAGE / fixed
            d = _duration(str(fp)) or 1.0
            self.per_scene = [(str(fp), seg["start"] % d) for seg in timeline]
            self.theme_bg = SynthwaveBackground
            self.seed, self.theme, self.cache = seed, theme, {}
            self.dim = 0.15
            return
        self.dim = 0.4
        for seg in timeline:
            sc = seg["scene"]
            text = " ".join(str(sc.get(k, "")) for k in ("say", "text", "question", "label", "bg_hint"))
            clip = best_clip(clips, text + " " + str(sc.get("bg_hint", "")), used)
            path = clip["path"] if clip else None
            if not path and stock_query and theme in ("news", "entertainment", "sports", "tech", "science", "money"):
                path = pexels_clip(sc.get("bg_hint") or stock_query)
            if path:
                used.add(path)
                d = _duration(path)
                start = random.uniform(0, max(0.0, d - (seg["end"] - seg["start"]) - 1))
            self.per_scene.append((path, start if path else 0.0))
        self.theme_bg = (THEMES.get(theme, SynthwaveBackground))
        self.seed = seed
        self.theme = theme
        self.cache = {}

    def frame(self, t):
        idx = next((i for i, s in enumerate(self.timeline) if s["start"] <= t < s["end"]), len(self.timeline) - 1)
        path, start = self.per_scene[idx]
        key = (idx, path)
        if key not in self.cache:
            for old in self.cache.values():  # one live decoder at a time
                getattr(old, "close", lambda: None)()
                getattr(getattr(old, "video", None), "close", lambda: None)()
            self.cache = {}
            if path and self.theme == "news":
                self.cache[key] = NewsTape(self.seed, path, start)
            elif path:
                self.cache[key] = VideoBackground(path, start, dim=self.dim)
            elif self.theme_bg is SynthwaveBackground:
                self.cache[key] = SynthwaveBackground(seed=self.seed, hue_shift=(self.seed % 3) / 3)
            elif self.theme_bg is Spotlight:
                self.cache[key] = Spotlight()
            else:
                self.cache[key] = self.theme_bg(self.seed)
        return self.cache[key].frame(t - self.timeline[idx]["start"])
