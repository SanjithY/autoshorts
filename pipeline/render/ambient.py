"""Background life for every stickman set, so the world keeps moving behind the main characters.

Everything here is drawn behind props and actors, smaller and fainter than the cast, so it reads as
"the world going on" rather than competing with the story.
"""
from __future__ import annotations

import math
import random

import skia

from .stick import GROUND, W, lerp, paint


# --------------------------------------------------------------- building blocks
def walker(c, x, y, s, t, color, facing=1, carry=None):
    """A small background stick figure walking."""
    ph = t * 7.5
    hip = (x, y - 105 * s)
    neck = (x + facing * 4 * s, y - 205 * s)
    head = (x + facing * 6 * s, y - 238 * s)
    w = 7 * s
    p = paint(color, w)
    for sgn in (1, -1):
        a = math.radians(26 * math.sin(ph) * sgn)
        kx, ky = hip[0] + facing * 52 * s * math.sin(a), hip[1] + 52 * s * math.cos(a)
        b = a - math.radians(max(0, 35 * math.sin(ph + 1.6 + (0 if sgn > 0 else math.pi))))
        c.drawLine(*hip, kx, ky, p)
        c.drawLine(kx, ky, kx + facing * 52 * s * math.sin(b), ky + 52 * s * math.cos(b), p)
        aa = math.radians(-22 * math.sin(ph) * sgn)
        c.drawLine(*neck, neck[0] + facing * 80 * s * math.sin(aa), neck[1] + 80 * s * math.cos(aa), p)
    c.drawLine(*hip, *neck, p)
    c.drawCircle(*head, 28 * s, paint(color, fill=True))
    if carry == "basket":
        c.drawRoundRect(skia.Rect.MakeXYWH(x + facing * 20 * s - 22 * s, y - 150 * s, 44 * s, 30 * s), 6, 6, paint(color, fill=True))
    elif carry == "umbrella":
        c.drawLine(neck[0], neck[1] + 20 * s, neck[0], neck[1] - 90 * s, paint(color, 4 * s))
        r = skia.Rect.MakeXYWH(neck[0] - 70 * s, neck[1] - 140 * s, 140 * s, 100 * s)
        c.drawArc(r, 180, 180, True, paint(color, fill=True))


def crowd_walkers(c, t, cam, n, y, s, color, seed, speed=(50, 90), carry=()):
    rnd = random.Random(seed)
    span = W + 600
    for i in range(n):
        d = 1 if rnd.random() < 0.5 else -1
        v = rnd.uniform(*speed)
        x0 = rnd.uniform(0, span)
        x = ((x0 + d * v * t) % span) - 300 - cam * 0.5
        walker(c, x, y + rnd.uniform(-10, 10), s * rnd.uniform(0.9, 1.1), t + i, color, d,
               rnd.choice(carry) if carry and rnd.random() < 0.5 else None)


def birds(c, t, n, seed, y0=220, y1=620, color=(40, 40, 55), speed=(70, 140), size=1.0):
    rnd = random.Random(seed)
    for i in range(n):
        v = rnd.uniform(*speed)
        x = (rnd.uniform(0, W + 300) + v * t) % (W + 300) - 150
        y = rnd.uniform(y0, y1) + 12 * math.sin(t * 1.3 + i)
        f = math.sin(t * rnd.uniform(9, 13) + i)
        s = rnd.uniform(10, 18) * size
        p = skia.Path()
        p.moveTo(x - s, y - s * 0.5 * f)
        p.quadTo(x - s * 0.4, y - s * 0.4, x, y)
        p.quadTo(x + s * 0.4, y - s * 0.4, x + s, y - s * 0.5 * f)
        c.drawPath(p, paint(color, 3.5))


def clouds(c, t, n, seed, color=(255, 255, 255), alpha=220, y0=200, y1=560, speed=12):
    rnd = random.Random(seed)
    for i in range(n):
        w = rnd.uniform(180, 320)
        x = (rnd.uniform(0, W + 500) + t * speed * rnd.uniform(0.6, 1.4)) % (W + 500) - 250
        y = rnd.uniform(y0, y1)
        pa = paint(color, fill=True, alpha=alpha)
        c.drawOval(skia.Rect.MakeXYWH(x, y, w, w * 0.3), pa)
        c.drawOval(skia.Rect.MakeXYWH(x + w * 0.2, y - w * 0.12, w * 0.45, w * 0.3), pa)


def smoke(c, x, y, t, seed=0, color=(235, 235, 240)):
    for i in range(6):
        k = ((t * 0.5 + i / 6 + seed * 0.13) % 1)
        r = 10 + 30 * k
        c.drawCircle(x + 30 * k + 6 * math.sin(t * 2 + i), y - 160 * k, r, paint(color, fill=True, alpha=int(170 * (1 - k))))


def distant_cars(c, t, y, n, seed, lights=False):
    rnd = random.Random(seed)
    for i in range(n):
        d = 1 if i % 2 else -1
        v = rnd.uniform(220, 380)
        x = ((rnd.uniform(0, W + 600) + d * v * t) % (W + 600)) - 300
        col = rnd.choice([(230, 70, 70), (70, 130, 220), (240, 200, 80), (230, 230, 235), (60, 60, 70)])
        c.drawRoundRect(skia.Rect.MakeXYWH(x - 46, y - 34, 92, 30), 8, 8, paint(col, fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(x - 26, y - 52, 52, 22), 6, 6, paint(col, fill=True))
        for wx in (-26, 26):
            c.drawCircle(x + wx, y - 4, 10, paint((25, 25, 30), fill=True))
        if lights:
            c.drawCircle(x + d * 46, y - 22, 6, paint((255, 240, 170), fill=True))


def falling(c, t, n, seed, color, size=8, speed=120, sway=40, y_max=GROUND):
    rnd = random.Random(seed)
    for i in range(n):
        x = rnd.uniform(0, W) + sway * math.sin(t * 1.5 + i)
        y = (rnd.uniform(0, y_max) + t * speed * rnd.uniform(0.6, 1.3)) % y_max
        c.save()
        c.translate(x, y)
        c.rotate(t * 120 + i * 30)
        c.drawOval(skia.Rect.MakeXYWH(-size, -size / 2, size * 2, size), paint(color, fill=True, alpha=220))
        c.restore()


def flag(c, x, y, t, color):
    c.drawLine(x, y, x, y - 160, paint((80, 70, 70), 5))
    p = skia.Path()
    p.moveTo(x, y - 160)
    for k in range(7):
        p.lineTo(x + k * 14, y - 160 + 6 * math.sin(t * 6 + k * 0.8))
    for k in range(6, -1, -1):
        p.lineTo(x + k * 14, y - 112 + 6 * math.sin(t * 6 + k * 0.8))
    p.close()
    c.drawPath(p, paint(color, fill=True))


# --------------------------------------------------------------- per-set life
def ambient(c, setting, t, cam=0.0):
    fade = lambda col: col
    if setting == "city_day":
        clouds(c, t, 4, 1)
        birds(c, t, 5, 2)
        distant_cars(c, t, GROUND - 2, 3, 3)
        crowd_walkers(c, t, cam, 5, GROUND - 6, 0.68, (90, 100, 130), 4, carry=("basket",))
    elif setting == "city_night":
        distant_cars(c, t, GROUND - 2, 3, 5, lights=True)
        crowd_walkers(c, t, cam, 4, GROUND - 6, 0.68, (70, 40, 100), 6)
        if int(t * 1.7) % 5 == 0:  # occasional shooting star
            k = (t * 1.7) % 1
            c.drawLine(800 - 500 * k, 200 + 160 * k, 860 - 500 * k, 180 + 160 * k, paint((255, 255, 255), 4, alpha=int(255 * (1 - k))))
    elif setting == "beach":
        birds(c, t, 5, 7, 250, 700, (255, 255, 255), size=1.3)
        crowd_walkers(c, t, cam, 3, GROUND - 4, 0.66, (160, 110, 90), 8, speed=(25, 50), carry=("umbrella",))
    elif setting == "town":
        clouds(c, t, 3, 9, y0=150, y1=380)
        for i, x in enumerate((90, 420, 770, 1010)):
            smoke(c, x - cam * 0.4, GROUND - 600 - (i % 2) * 40, t, i)
        birds(c, t, 6, 10, 160, 420, (70, 60, 70))
        crowd_walkers(c, t, cam, 5, GROUND - 4, 0.7, (105, 75, 85), 11, speed=(35, 70), carry=("basket",))
    elif setting == "field":
        clouds(c, t, 4, 12, y0=180, y1=520, speed=18)
        birds(c, t, 7, 13, 300, 700, (60, 50, 60))
        rnd = random.Random(14)
        for i in range(10):  # dust puffs drifting over the wheat
            k = (t * 0.4 + i / 10) % 1
            x = (rnd.uniform(0, W) + 200 * k) % W
            c.drawCircle(x, GROUND - 40 - 60 * k, 14 + 26 * k, paint((230, 200, 150), fill=True, alpha=int(120 * (1 - k))))
    elif setting == "ocean":
        for i, fx in enumerate((-260, -90, 80, 250)):  # smoke from the liner's funnels
            smoke(c, 760 - cam * 0.3 + (fx + 32) * 0.42, 1000 - 270 * 0.42, t, i, (180, 180, 200))
        birds(c, t, 3, 15, 500, 800, (220, 220, 235))
        if int(t * 1.3) % 4 == 0:
            k = (t * 1.3) % 1
            c.drawLine(900 - 600 * k, 150 + 200 * k, 960 - 600 * k, 130 + 200 * k, paint((255, 255, 255), 4, alpha=int(255 * (1 - k))))
    elif setting == "paris":
        distant_cars(c, t, GROUND - 2, 3, 16, lights=True)
        crowd_walkers(c, t, cam, 4, GROUND - 6, 0.68, (60, 60, 80), 17, carry=("umbrella", "basket"))
        birds(c, t, 4, 18, 250, 500, (40, 40, 60))
    elif setting == "forest":
        falling(c, t, 18, 19, (200, 120, 60), size=9, speed=160, sway=90)
        birds(c, t, 3, 20, 200, 500, (30, 30, 40), speed=(160, 240))
    elif setting == "stadium":
        for i, x in enumerate((60, 330, 600, 870)):
            flag(c, x - cam * 0.3, 640, t + i, [(230, 60, 60), (60, 110, 220), (240, 240, 240), (240, 190, 60)][i])
        rnd = random.Random(int(t * 5))
        for i in range(3):  # camera flashes in the crowd
            c.drawCircle(rnd.uniform(0, W), rnd.uniform(660, 1230), 9, paint((255, 255, 240), fill=True, alpha=230))
    elif setting == "room":
        # ceiling fan + wall clock
        cx, cy = 540, 160
        c.drawLine(cx, 0, cx, cy, paint((90, 70, 60), 6))
        for k in range(3):
            a = t * 6 + k * 2.094
            c.drawOval(skia.Rect.MakeXYWH(cx + 130 * math.cos(a) - 70, cy - 10 + 18 * math.sin(a), 140, 22), paint((120, 90, 70), fill=True))
        c.drawCircle(cx, cy, 22, paint((90, 70, 60), fill=True))
        kx, ky = 430, 470
        c.drawCircle(kx, ky, 54, paint((255, 255, 255), fill=True))
        c.drawCircle(kx, ky, 54, paint((90, 70, 60), 6))
        c.drawLine(kx, ky, kx + 40 * math.sin(t * 2), ky - 40 * math.cos(t * 2), paint((40, 30, 30), 4))
        c.drawLine(kx, ky, kx + 26 * math.sin(t * 0.2), ky - 26 * math.cos(t * 0.2), paint((40, 30, 30), 6))
    elif setting == "stage":
        rnd = random.Random(22)
        for i in range(16):  # audience heads bobbing in the foreground
            x = i * 72 + 20
            b = 8 * abs(math.sin(t * 5 + rnd.uniform(0, 6)))
            c.drawCircle(x, GROUND + 400 - b, 40, paint((30, 20, 45), fill=True))
            c.drawLine(x, GROUND + 440 - b, x, GROUND + 520, paint((30, 20, 45), 34))
    elif setting == "news_desk":
        txt = "  BREAKING  ·  MORE AT ELEVEN  ·  STAY TUNED  ·  "
        from .stick import typeface
        font = skia.Font(typeface(), 40)
        w = font.measureText(txt)
        x0 = -((t * 160) % w)
        c.drawRect(skia.Rect.MakeXYWH(-400, GROUND - 270, W + 800, 56), paint((20, 20, 40), fill=True))
        for k in range(3):
            c.drawString(txt, x0 + k * w, GROUND - 228, font, paint((255, 255, 255), fill=True))
