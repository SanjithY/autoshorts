"""The channel's "Disco" look, shared by every format.

Dark glassy cards, a pink→orange gradient accent, pill labels, gradient rank badges,
story-style progress segments, rounded white-framed media, soft animated backdrop.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .core import BLACK, H, W, WHITE, YELLOW, ease_out_back, ease_out_cubic, font, paste, text_sprite, wrap

PINK, ORANGE = (255, 46, 120), (255, 150, 40)
CARD = (10, 10, 18, 205)
MARK = (254, 0, 254)          # sentinel colour swapped for the gradient
CAPTION_Y = 1330
CENTER_Y = 760


def gradient(w, h, c1=PINK, c2=ORANGE, horizontal=True):
    n = w if horizontal else h
    x = np.linspace(0, 1, max(n, 1))
    g = (np.array(c1)[None, :] * (1 - x[:, None]) + np.array(c2)[None, :] * x[:, None]).astype(np.uint8)
    arr = np.broadcast_to(g[None, :, :], (h, w, 3)) if horizontal else np.broadcast_to(g[:, None, :], (h, w, 3))
    return Image.fromarray(np.ascontiguousarray(arr))


@lru_cache(maxsize=64)
def round_mask(w, h, r):
    m = Image.new("L", (w * 2, h * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * 2 - 1, h * 2 - 1), r * 2, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def gtext(text, kind="display", size=120, max_w=940, highlight=(), stroke=0, all_grad=False, line_gap=0.0):
    """Text sprite whose highlighted words (or all words) are filled with the disco gradient."""
    spr = text_sprite(text, kind, size, MARK if all_grad else WHITE, stroke, BLACK, max_w, True, line_gap,
                      tuple(w.upper() for w in highlight), MARK)
    arr = np.asarray(spr).copy()
    rgb = arr[:, :, :3].astype(int)
    m = (rgb[:, :, 0] > 170) & (rgb[:, :, 1] < 90) & (rgb[:, :, 2] > 170)
    if m.any():
        g = np.asarray(gradient(spr.width, spr.height))
        arr[:, :, :3][m] = g[m]
    return Image.fromarray(arr)


def card(w, h, r=34, fill=CARD, accent=True):
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(c).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=fill)
    if accent:
        c.paste(gradient(w - 2 * r, 8), (r, h - 8), round_mask(w - 2 * r, 8, 4))
    return c


def pill(text, size=36, grad=False, dot=True, kind="black", pad=28):
    t = text_sprite(text.upper(), kind, size, WHITE, 0, BLACK, 980, False, 0.0)
    w, h = t.width + pad * 2 + (26 if dot else 0), t.height + 16
    if grad:
        p = gradient(w, h).convert("RGBA")
        p.putalpha(round_mask(w, h, h // 2))
    else:
        p = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(p).rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=(0, 0, 0, 170))
    if dot and not grad:
        ImageDraw.Draw(p).ellipse((pad - 6, h // 2 - 7, pad + 8, h // 2 + 7), fill=PINK)
    p.alpha_composite(t, (pad + (26 if dot and not grad else 0), 8))
    return p


def badge(label, size=196, font_size=120):
    g = gradient(size, size).convert("RGBA")
    g.putalpha(round_mask(size, size, size // 4))
    num = text_sprite(label, "display", font_size, WHITE, 0, BLACK, size * 2, True, 0.0)
    if num.width > size - 16:
        num = num.resize((size - 16, int(num.height * (size - 16) / num.width)), Image.LANCZOS)
    g.alpha_composite(num, ((size - num.width) // 2, (size - num.height) // 2 + 4))
    return g


def fit_lines(text, box_w, max_lines, sizes=(76, 68, 62, 56, 50, 44), kind="black"):
    for s in sizes:
        f = font(kind, s)
        lines = wrap(text, f, box_w)
        if len(lines) <= max_lines and max(f.getlength(l) for l in lines) <= box_w:
            return s, lines
    f = font(kind, sizes[-1])
    return sizes[-1], wrap(text, f, box_w)[:max_lines]


def text_card(text, w=1000, max_lines=3, highlight=(), sizes=(76, 68, 62, 56, 50, 44), left=None, min_h=0):
    """Dark card holding wrapped text; highlight words get the gradient. left = width reserved on the left."""
    pad_l = (left or 0) + 50
    size, lines = fit_lines(text.upper(), w - pad_l - 44, max_lines, sizes)
    f = font("black", size)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.04)
    h = max(min_h, lh * len(lines) + 70)
    c = card(w, h)
    body = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    hl = {x.upper().strip(".,!?") for x in highlight}
    y0 = (h - lh * len(lines)) // 2 - 4
    for i, ln in enumerate(lines):
        x = pad_l
        for word in ln.split(" "):
            col = MARK if word.strip(".,!?") in hl else WHITE
            d.text((x + 3, y0 + i * lh + 4), word, font=f, fill=(0, 0, 0, 150))
            d.text((x, y0 + i * lh), word, font=f, fill=col)
            x += f.getlength(word + " ")
    arr = np.asarray(body).copy()
    m = (arr[:, :, 0] > 170) & (arr[:, :, 1] < 90) & (arr[:, :, 2] > 170) & (arr[:, :, 3] > 0)
    if m.any():
        arr[:, :, :3][m] = np.asarray(gradient(w, h))[m]
    c.alpha_composite(Image.fromarray(arr))
    return c


def progress_segments(frame, n, idx, p, y=112):
    d = ImageDraw.Draw(frame)
    gap, x0, x1 = 10, 40, W - 40
    sw = (x1 - x0 - gap * (n - 1)) / max(n, 1)
    for i in range(n):
        xa = x0 + i * (sw + gap)
        d.rounded_rectangle((xa, y, xa + sw, y + 8), 4, fill=(90, 90, 100))
        fill = 1.0 if i < idx else (p if i == idx else 0)
        if fill > 0:
            d.rounded_rectangle((xa, y, xa + max(8, sw * fill), y + 8), 4, fill=WHITE)


@lru_cache(maxsize=4)
def scrim():
    """Dark gradient at the top and bottom so cards and captions read on any background."""
    a = np.zeros((H, 1), np.float32)
    y = np.arange(H)
    a[:, 0] = np.clip((420 - y) / 420, 0, 1) * 150 + np.clip((y - 1150) / 600, 0, 1) * 170
    alpha = np.repeat(a, W, axis=1).astype(np.uint8)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.putalpha(Image.fromarray(alpha))
    return img


class DiscoBackground:
    """Deep purple stage with slow-moving pink/orange light blobs and a faint dot grid."""

    def __init__(self, seed=0):
        rnd = np.random.default_rng(seed)
        self.blobs = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(260, 520), c, rnd.uniform(0, 6))
                      for c in (PINK, ORANGE, (120, 60, 255), PINK, (0, 200, 255))]
        base = Image.new("RGB", (W // 4, H // 4), (14, 8, 30))
        self.base = base
        dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dots)
        for x in range(30, W, 60):
            for yy in range(30, H, 60):
                dd.ellipse((x - 2, yy - 2, x + 2, yy + 2), fill=(255, 255, 255, 22))
        self.dots = dots

    def frame(self, t):
        img = self.base.copy()
        d = ImageDraw.Draw(img)
        for x, y, r, c, ph in self.blobs:
            cx = (x + 180 * math.sin(t * 0.35 + ph)) / 4
            cy = (y + 240 * math.cos(t * 0.28 + ph)) / 4
            rr = r / 4
            d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=tuple(int(v * 0.55) for v in c))
        img = img.filter(ImageFilter.GaussianBlur(28)).resize((W, H), Image.BICUBIC)
        img.paste(self.dots, (0, 0), self.dots)
        return img


def star_shape(d, cx, cy, r, fill, outline=WHITE, width=5):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill, outline=outline, width=width)
