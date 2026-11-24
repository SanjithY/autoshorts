"""Low-level drawing helpers: fonts, text sprites, easing, backgrounds, captions, encoding."""
from __future__ import annotations

import math
import random
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FPS = 30
ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = ROOT / "assets" / "fonts"

# Vice-City-at-dusk palette (original, not Rockstar's branding)
PINK = (255, 64, 160)
HOT = (255, 46, 99)
ORANGE = (255, 149, 40)
YELLOW = (255, 221, 51)
TEAL = (0, 229, 255)
PURPLE = (120, 40, 200)
NIGHT = (18, 8, 40)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (60, 230, 120)

# TikTok/Shorts UI safe zone: keep text out of bottom ~18% and right ~12%
SAFE_TOP, SAFE_BOTTOM = 150, int(H * 0.80)
CAPTION_Y = 1330


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out_cubic(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_out_back(t, s=1.9):
    t = clamp(t)
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def ease_in_out(t):
    t = clamp(t)
    return 0.5 - 0.5 * math.cos(math.pi * t)


def prog(t, start, dur):
    return clamp((t - start) / dur) if dur > 0 else 1.0


# ---------------------------------------------------------------- fonts
@lru_cache(maxsize=64)
def font(kind: str, size: int):
    if kind == "display":
        return ImageFont.truetype(str(FONT_DIR / "Anton-Regular.ttf"), size)
    f = ImageFont.truetype(str(FONT_DIR / "Montserrat.ttf"), size)
    weight = {"bold": 800, "black": 900, "medium": 600, "regular": 500}.get(kind, 800)
    f.set_variation_by_axes([weight])
    return f


def wrap(text: str, fnt, max_w: int):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if fnt.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


@lru_cache(maxsize=512)
def text_sprite(text: str, kind="display", size=120, fill=WHITE, stroke=8,
                stroke_fill=BLACK, max_w=900, shadow=True, line_gap=0.05,
                highlight: tuple = (), hl_fill=YELLOW):
    """Centered multi-line text as an RGBA image. `highlight` = words to color."""
    fnt = font(kind, size)
    # shrink to fit width if a single word is too wide
    while size > 30 and max(fnt.getlength(w) for w in text.split() or [" "]) > max_w:
        size = int(size * 0.92)
        fnt = font(kind, size)
    lines = wrap(text, fnt, max_w)
    asc, desc = fnt.getmetrics()
    lh = int((asc + desc) * (1 + line_gap))
    pad = stroke + 14
    widths = [int(fnt.getlength(l)) for l in lines]
    img = Image.new("RGBA", (max(widths) + pad * 2, lh * len(lines) + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    hl = {h.upper().strip(".,!?") for h in highlight}
    for i, line in enumerate(lines):
        x = pad + (max(widths) - widths[i]) // 2
        y = pad + i * lh
        if shadow:
            d.text((x + 6, y + 8), line, font=fnt, fill=(0, 0, 0, 150),
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 150))
        cx = x
        for w in line.split(" "):
            col = hl_fill if w.upper().strip(".,!?") in hl else fill
            d.text((cx, y), w, font=fnt, fill=col, stroke_width=stroke, stroke_fill=stroke_fill)
            cx += fnt.getlength(w + " ")
    return img


def paste(frame: Image.Image, sprite: Image.Image, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    if scale <= 0.01 or alpha <= 0.01:
        return
    s = sprite
    if abs(scale - 1) > 0.01:
        s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))), Image.BILINEAR)
    if rot:
        s = s.rotate(rot, resample=Image.BILINEAR, expand=True)
    if alpha < 0.99:
        a = s.getchannel("A").point(lambda v: int(v * alpha))
        s = s.copy()
        s.putalpha(a)
    frame.alpha_composite(s, (int(cx - s.width / 2), int(cy - s.height / 2))) if frame.mode == "RGBA" \
        else frame.paste(s, (int(cx - s.width / 2), int(cy - s.height / 2)), s)


def rounded_box(w, h, fill, radius=28, outline=None, width=0):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=fill,
                                          outline=outline, width=width)
    return img


def star_points(cx, cy, r_out, r_in, n=5, rot=-math.pi / 2):
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = rot + i * math.pi / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# ---------------------------------------------------------------- backgrounds
class SynthwaveBackground:
    """Original animated dusk scene: gradient sky, striped sun, palms, moving neon grid."""

    def __init__(self, seed=0, hue_shift=0):
        rnd = random.Random(seed)
        self.rnd = rnd
        y = np.linspace(0, 1, H)[:, None]
        top = np.array(NIGHT, float)
        mid = np.array(PURPLE, float) * (1 - hue_shift) + np.array((20, 60, 140), float) * hue_shift
        low = np.array(HOT, float)
        sky = np.where(y < 0.5, top + (mid - top) * (y / 0.5),
                       mid + (low - mid) * ((y - 0.5) / 0.12).clip(0, 1))  # (H,3)
        base = Image.fromarray(np.ascontiguousarray(
            np.broadcast_to(sky[:, None, :], (H, W, 3))).astype(np.uint8))
        self.horizon = int(H * 0.62)
        d = ImageDraw.Draw(base)
        # stars
        for _ in range(140):
            sx, sy = rnd.randrange(W), rnd.randrange(int(H * 0.45))
            b = rnd.randrange(120, 255)
            d.point((sx, sy), fill=(b, b, b))
        # sun with stripes
        sun = Image.new("RGBA", (620, 620), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sun)
        for i in range(620):
            t = i / 620
            col = tuple(int(YELLOW[k] * (1 - t) + PINK[k] * t) for k in range(3))
            sd.line([(0, i), (620, i)], fill=col + (255,))
        mask = Image.new("L", (620, 620), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse((0, 0, 619, 619), fill=255)
        for k in range(7):
            yy = 330 + k * 40
            md.rectangle((0, yy, 620, yy + 6 + k * 3), fill=0)
        sun.putalpha(mask)
        glow = sun.filter(ImageFilter.GaussianBlur(40))
        base.paste(glow, (W // 2 - 310, self.horizon - 470), glow)
        base.paste(sun, (W // 2 - 310, self.horizon - 470), sun)
        # ground
        d.rectangle((0, self.horizon, W, H), fill=(14, 4, 30))
        self._palms(base)
        self.base = base

    def _palms(self, img):
        """City skyline silhouette with lit windows along the horizon."""
        d = ImageDraw.Draw(img)
        rnd = self.rnd
        x = -20
        while x < W:
            bw = rnd.randrange(50, 130)
            bh = rnd.randrange(60, 330) if abs(x - W / 2) > 260 else rnd.randrange(40, 140)
            top = self.horizon - bh
            d.rectangle((x, top, x + bw, self.horizon), fill=(16, 4, 34))
            if rnd.random() < 0.3:
                d.rectangle((x + bw // 2 - 2, top - 40, x + bw // 2 + 2, top), fill=(16, 4, 34))
            for wy in range(top + 12, self.horizon - 10, 22):
                for wx in range(x + 8, x + bw - 8, 18):
                    if rnd.random() < 0.28:
                        c = rnd.choice([YELLOW, PINK, TEAL, ORANGE])
                        d.rectangle((wx, wy, wx + 6, wy + 9), fill=c)
            x += bw + rnd.randrange(0, 14)

    def frame(self, t: float) -> Image.Image:
        img = self.base.copy()
        d = ImageDraw.Draw(img)
        hz = self.horizon
        # perspective grid
        off = (t * 0.9) % 1.0
        for i in range(14):
            z = (i + off) / 14
            yy = hz + int((H - hz) * z ** 2.2)
            c = int(120 + 135 * z)
            d.line([(0, yy), (W, yy)], fill=(c, 30, c // 2 + 60), width=2 + int(z * 3))
        for k in range(-12, 13):
            d.line([(W // 2 + k * 30, hz), (W // 2 + k * 260, H)], fill=(200, 40, 160), width=2)
        d.line([(0, hz), (W, hz)], fill=PINK, width=4)
        return img


class BlankBackground:
    def frame(self, t):
        return Image.new("RGB", (W, H), NIGHT)


class VideoBackground:
    """Uses the user's own gameplay footage, cropped to 9:16, dimmed, streamed via ffmpeg."""

    def __init__(self, path: str, start: float = 0.0, dim=0.45):
        self.dim = dim
        cmd = ["ffmpeg", "-v", "quiet", "-ss", str(start), "-i", path, "-an",
               "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.last = Image.new("RGB", (W, H), NIGHT)

    def close(self):
        try:
            self.p.kill()
            self.p.wait(timeout=5)
        except Exception:
            pass

    def frame(self, t: float) -> Image.Image:
        buf = self.p.stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            arr = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            self.last = Image.fromarray((arr * (1 - self.dim)).astype(np.uint8))
        return self.last.copy()


# ---------------------------------------------------------------- captions
def caption_chunks(words: list[dict], max_words=3):
    """Group timed words [{w,start,end}] into short on-screen chunks."""
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or w["w"].endswith((".", "!", "?", ",")):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def draw_caption(frame, chunks, t, y=CAPTION_Y):
    for ch in chunks:
        if ch[0]["start"] - 0.05 <= t < ch[-1]["end"] + 0.12:
            active = next((w["w"] for w in ch if w["start"] <= t < w["end"] + 0.05), "")
            text = " ".join(w["w"] for w in ch).upper()
            spr = text_sprite(text, "black", 82, WHITE, 9, BLACK, 880, True, 0.0,
                              highlight=(active.upper(),) if active else ())
            age = t - ch[0]["start"]
            sc = 0.85 + 0.15 * ease_out_back(age / 0.18)
            paste(frame, spr, W / 2, y, sc)
            return


def draw_progress(frame, t, total):
    d = ImageDraw.Draw(frame)
    d.rectangle((0, 0, W, 10), fill=(0, 0, 0))
    d.rectangle((0, 0, int(W * clamp(t / total)), 10), fill=YELLOW)


# ---------------------------------------------------------------- encoding
class Encoder:
    def __init__(self, out_path: str, audio_path: str | None):
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
        if audio_path:
            cmd += ["-i", audio_path, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "44100",
                    "-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", out_path]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, img: Image.Image):
        self.p.stdin.write(img.convert("RGB").tobytes())

    def close(self):
        self.p.stdin.close()
        if self.p.wait() != 0:
            raise RuntimeError("ffmpeg encode failed")
