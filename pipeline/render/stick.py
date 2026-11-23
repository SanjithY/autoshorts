"""Stickman animation engine (skia, antialiased vector drawing).

A scene is plain JSON, e.g.
  {"type": "stick", "setting": "city_night", "say": "...",
   "actors": [{"id": "a", "x": 0.3, "action": "walk", "to": 0.6, "face": "happy", "hat": "cap", "color": "#ff2e63"},
              {"id": "b", "x": 0.75, "action": "shocked", "facing": -1}],
   "props": [{"kind": "car", "x": 0.2, "move_to": 0.9, "color": "#00e5ff"}],
   "bubble": {"actor": "b", "text": "SIX STARS?!"},
   "fx": ["police_lights", "speed_lines"], "camera": "zoom_in", "title": "OPTIONAL BIG TEXT"}

Actors keep their position/pose between scenes (same id), so motion flows across cuts.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import skia

W, H = 1080, 1920
GROUND = 1400
ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = ROOT / "assets" / "fonts"

# --------------------------------------------------------------- helpers


def rgb(c, a=255):
    if isinstance(c, str):
        c = c.lstrip("#")
        c = tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return skia.ColorSetARGB(a, *c[:3])


def lerp(a, b, t):
    return a + (b - a) * t


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_back(t, s=1.7):
    t = max(0.0, min(1.0, t)) - 1
    return t * t * ((s + 1) * t + s) + 1


@lru_cache(maxsize=8)
def typeface(name="Anton-Regular.ttf"):
    return skia.Typeface.MakeFromFile(str(FONT_DIR / name))


def paint(color, width=0, fill=False, alpha=255, cap=True):
    p = skia.Paint(AntiAlias=True, Color=rgb(color, alpha))
    if fill:
        p.setStyle(skia.Paint.kFill_Style)
    else:
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(width)
        if cap:
            p.setStrokeCap(skia.Paint.kRound_Cap)
            p.setStrokeJoin(skia.Paint.kRound_Join)
    return p


def wrap_text(text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.measureText(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# --------------------------------------------------------------- poses
# Angles in degrees. Limbs: 0 = straight down, + = toward facing direction.
# *2 values are relative bends of the lower segment.
BASE = dict(torso=0, head=0, la1=-12, la2=10, ra1=12, ra2=10, ll1=-6, ll2=0, rl1=6, rl2=0, dy=0.0)
KEYS = list(BASE)


def pose(**kw):
    p = dict(BASE)
    p.update(kw)
    return p


def blend(p, q, t):
    return {k: lerp(p[k], q[k], t) for k in KEYS}


def act_pose(action, t, actor):
    """Pose for an action at local time t (seconds)."""
    s = math.sin
    a = action
    if a in ("idle", "stand", "listen"):
        b = s(t * 2.2)
        return pose(torso=1.5 * b, head=2 * s(t * 1.3), la1=-10 + 2 * b, ra1=10 - 2 * b, dy=-2 * abs(b))
    if a == "talk":
        g = s(t * 5.5)
        return pose(torso=3 + 2 * s(t * 2), head=4 * s(t * 3.1), la1=-15, la2=20, ra1=35 + 25 * g, ra2=60 + 30 * s(t * 4),
                    dy=-3 * abs(s(t * 2.5)))
    if a == "explain":  # both hands presenting
        g = s(t * 3)
        return pose(torso=4, head=3 * s(t * 2), la1=40 + 10 * g, la2=50, ra1=55 - 10 * g, ra2=45, dy=-2 * abs(g))
    if a in ("walk", "sneak"):
        p_ = t * (7.5 if a == "walk" else 5)
        k = 1 if a == "walk" else 0.7
        po = pose(torso=4 if a == "walk" else 22, head=-2,
                  ll1=28 * k * s(p_), ll2=-max(0, 40 * s(p_ + 1.6)) * k,
                  rl1=-28 * k * s(p_), rl2=-max(0, 40 * s(p_ + 1.6 + math.pi)) * k,
                  la1=-22 * s(p_), la2=15, ra1=22 * s(p_), ra2=15, dy=-6 * abs(s(p_)))
        if a == "sneak":
            po.update(la1=60, la2=-70, ra1=40, ra2=-60, dy=25)
        return po
    if a == "run":
        p_ = t * 12
        return pose(torso=16, head=-6, ll1=48 * s(p_), ll2=-max(10, 85 * s(p_ + 1.4)),
                    rl1=-48 * s(p_), rl2=-max(10, 85 * s(p_ + 1.4 + math.pi)),
                    la1=-50 * s(p_), la2=95, ra1=50 * s(p_), ra2=95, dy=-14 * abs(s(p_)))
    if a == "jump":
        c = t % 1.6
        if c < 0.3:   # anticipation
            k = ease(c / 0.3)
            return pose(torso=12 * k, ll1=35 * k, ll2=-70 * k, rl1=30 * k, rl2=-65 * k, la1=-40 * k, ra1=-35 * k)
        if c < 0.85:  # airborne
            k = (c - 0.3) / 0.55
            return pose(torso=-4, la1=-150, la2=-10, ra1=150, ra2=10, ll1=20, ll2=-50, rl1=-10, rl2=-30,
                        dy=-260 * math.sin(math.pi * k))
        k = ease((c - 0.85) / 0.25)
        return blend(pose(torso=14, ll1=35, ll2=-70, rl1=30, rl2=-65, la1=30, ra1=-30), act_pose("idle", t, actor), k)
    if a in ("celebrate", "cheer"):
        b = abs(s(t * 7))
        return pose(torso=-4, head=-8, la1=-155 + 15 * b, la2=-20, ra1=155 - 15 * b, ra2=20, ll1=-10, rl1=10, dy=-70 * b)
    if a == "dance":
        p_ = t * 6
        return pose(torso=10 * s(p_), head=8 * s(p_ + 1), la1=-90 + 60 * s(p_), la2=-60, ra1=90 + 60 * s(p_ + 1), ra2=60,
                    ll1=-20 + 20 * s(p_), ll2=-30 * abs(s(p_)), rl1=20 + 20 * s(p_), rl2=-30 * abs(s(p_ + 1.5)),
                    dy=-18 * abs(s(p_)))
    if a == "wave":
        return pose(head=5, la1=-10, ra1=150, ra2=25 + 30 * s(t * 9), dy=-2 * abs(s(t * 2)))
    if a == "point":
        return pose(torso=6, head=4, ra1=95, ra2=0, la1=-10, la2=15, dy=-2 * abs(s(t * 2)))
    if a == "shrug":
        k = ease_out(min(1, t / 0.35))
        b = 0.5 + 0.5 * s(t * 3)
        return pose(head=10 * k * b, la1=-60 * k, la2=-110 * k, ra1=60 * k, ra2=110 * k, dy=-6 * k)
    if a == "facepalm":
        k = ease_out(min(1, t / 0.4))
        return pose(torso=10 * k, head=18 * k, ra1=150 * k, ra2=120 * k, la1=-12, dy=4 * k)
    if a == "think":
        return pose(head=-8 + 2 * s(t * 1.5), ra1=40, ra2=130, la1=25, la2=-80, torso=2)
    if a in ("shocked", "shock"):
        k = ease_back(min(1, t / 0.3))
        sh = s(t * 40) * 3 * max(0, 1 - t / 0.6)
        return pose(torso=-14 * k + sh, head=-10 * k, la1=-120 * k, la2=-40 * k, ra1=120 * k, ra2=40 * k, ll1=-14, rl1=14,
                    dy=-30 * k * max(0, 1 - t / 0.5))
    if a == "sad":
        b = s(t * 1.2)
        return pose(torso=14, head=26 + 2 * b, la1=8, la2=0, ra1=4, ra2=0, dy=10)
    if a == "angry":
        g = abs(s(t * 9))
        return pose(torso=10, head=8, la1=40, la2=110, ra1=60 + 30 * g, ra2=100, ll1=-12, rl1=12, dy=-6 * g)
    if a == "fall":
        k = ease(min(1, t / 0.6))
        return pose(torso=-75 * k, head=-20 * k, la1=-120 * k, ra1=-160 * k, ll1=60 * k, rl1=90 * k, ll2=-20 * k,
                    dy=40 * ease(min(1, t / 0.6)))
    if a == "sit":
        return pose(torso=-4, ll1=90, ll2=-90, rl1=85, rl2=-85, la1=30, la2=40, ra1=35, ra2=40, dy=0)
    if a == "phone":
        return pose(head=22, la1=35, la2=105, ra1=30, ra2=110, torso=3 + s(t * 2), dy=-2 * abs(s(t * 2)))
    if a == "drive":  # seated, hands on wheel (used inside car prop)
        return pose(torso=-6, la1=70, la2=-20, ra1=75, ra2=-25, ll1=85, ll2=-80, rl1=85, rl2=-80, head=-3 + 2 * s(t * 3))
    if a == "count_money":
        g = s(t * 10)
        return pose(head=20, la1=40, la2=90, ra1=55 + 15 * g, ra2=85, torso=4)
    if a == "flex":
        k = ease_back(min(1, t / 0.35))
        return pose(la1=-90 * k, la2=-110 * k, ra1=90 * k, ra2=110 * k, head=-6, dy=-4 * abs(s(t * 4)))
    if a == "bow":
        k = ease(min(1, t / 0.5))
        return pose(torso=55 * k, head=10 * k, la1=10, ra1=40 * k, ra2=60 * k)
    return act_pose("idle", t, actor)


MOVING = {"walk": 260, "run": 620, "sneak": 160}  # px per second


@dataclass
class Actor:
    id: str
    x: float = 540
    facing: int = 1
    color: tuple = (20, 20, 28)
    accent: tuple = (255, 46, 99)
    hat: str = ""
    face: str = "neutral"
    scale: float = 1.45
    prop: str = ""
    last_pose: dict = field(default_factory=lambda: dict(BASE))
    stars: int = 0


# --------------------------------------------------------------- drawing the figure
L = dict(torso=138, neck=16, head=60, ua=86, fa=82, th=104, sh=104)


def _seg(x, y, ang_deg, length, facing):
    a = math.radians(ang_deg)
    return x + facing * length * math.sin(a), y + length * math.cos(a)


def figure_points(actor, p):
    """Forward kinematics. Returns dict of joint positions (world coords)."""
    f, sc = actor.facing, actor.scale
    k = {n: v * sc for n, v in L.items()}
    tor = math.radians(p["torso"])
    # legs relative to a hip at (0,0)
    def leg(a1, a2):
        kx, ky = _seg(0, 0, a1, k["th"], f)
        fx, fy = _seg(kx, ky, a1 + a2, k["sh"], f)
        return (kx, ky), (fx, fy)
    lk, lf = leg(p["ll1"], p["ll2"])
    rk, rf = leg(p["rl1"], p["rl2"])
    foot_low = max(lf[1], rf[1])
    dy = p["dy"]
    hip = (actor.x, GROUND - foot_low - 4 + (dy if dy < 0 else dy * 0.35))
    neck = (hip[0] + f * k["torso"] * math.sin(tor), hip[1] - k["torso"] * math.cos(tor))
    hang = tor + math.radians(p["head"])
    head = (neck[0] + f * (k["neck"] + k["head"]) * math.sin(hang), neck[1] - (k["neck"] + k["head"]) * math.cos(hang))
    sh = (lerp(neck[0], hip[0], 0.08), lerp(neck[1], hip[1], 0.08))

    def arm(a1, a2):
        ex, ey = _seg(sh[0], sh[1], a1 + p["torso"], k["ua"], f)
        hx, hy = _seg(ex, ey, a1 + p["torso"] + a2, k["fa"], f)
        return (ex, ey), (hx, hy)
    le, lh = arm(p["la1"], p["la2"])
    re, rh = arm(p["ra1"], p["ra2"])
    off = lambda q: (hip[0] + q[0], hip[1] + q[1])
    return dict(hip=hip, neck=neck, head=head, sh=sh, le=le, lh=lh, re=re, rh=rh,
                lk=off(lk), lf=off(lf), rk=off(rk), rf=off(rf), hang=hang)


def draw_face(c, actor, j, t, talking):
    hx, hy = j["head"]
    r = L["head"] * actor.scale
    f = actor.facing
    ex = hx + f * r * 0.32
    face = actor.face
    eye_r = 6.5 * actor.scale * (1.5 if face in ("shock", "shocked") else 1)
    blink = (t % 3.7) < 0.12
    ink = paint((20, 20, 28), fill=True)
    for dx in (-0.22, 0.2):
        x = ex + f * r * dx
        if blink:
            c.drawLine(x - eye_r, hy - r * 0.12, x + eye_r, hy - r * 0.12, paint((20, 20, 28), 4))
        else:
            c.drawCircle(x, hy - r * 0.12, eye_r, ink)
    if face == "angry":
        for dx, s_ in ((-0.22, 1), (0.2, -1)):
            x = ex + f * r * dx
            c.drawLine(x - 15, hy - r * 0.4 - 8 * s_ * f, x + 15, hy - r * 0.4 + 8 * s_ * f, paint((20, 20, 28), 7))
    my = hy + r * 0.32
    k = actor.scale
    mp = paint((20, 20, 28), 5 * k)
    open_ = talking and (math.sin(t * 22) > -0.2)
    path = skia.Path()
    if face in ("shock", "shocked") or (open_ and face not in ("sad",)):
        rr = (11 if face in ("shock", "shocked") else 7 + 4 * abs(math.sin(t * 22))) * k
        c.drawOval(skia.Rect.MakeXYWH(ex - 9 * k, my - rr * 0.6, 18 * k, rr * 1.3), paint((20, 20, 28), fill=True))
        return
    if face in ("happy", "smug", "excited"):
        path.moveTo(ex - 16 * k, my - 4 * k)
        path.quadTo(ex, my + (14 if face != "smug" else 6) * k, ex + 16 * k, my - (4 if face != "smug" else 10) * k)
    elif face in ("sad", "angry"):
        path.moveTo(ex - 15 * k, my + 6 * k)
        path.quadTo(ex, my - 8 * k, ex + 15 * k, my + 6 * k)
    else:
        path.moveTo(ex - 12 * k, my)
        path.lineTo(ex + 12 * k, my)
    c.drawPath(path, mp)


def draw_actor(c, actor, p, t, talking=False):
    j = figure_points(actor, p)
    w = 15 * actor.scale
    # light outline under the whole figure so it pops on any background
    halo = paint((255, 255, 255), w + 12, alpha=235)
    for a, b in (("hip", "lk"), ("lk", "lf"), ("sh", "le"), ("le", "lh"), ("hip", "neck"),
                 ("hip", "rk"), ("rk", "rf"), ("sh", "re"), ("re", "rh")):
        c.drawLine(*j[a], *j[b], halo)
    c.drawCircle(*j["head"], L["head"] * actor.scale + 9, paint((255, 255, 255), fill=True, alpha=235))
    ink = paint(actor.color, w)
    back = paint(tuple(min(255, v + 70) for v in actor.color[:3]) if sum(actor.color[:3]) < 200 else
                 tuple(max(0, v - 70) for v in actor.color[:3]), w)
    # back limbs first (slightly lighter) for depth
    for a, b, cc in ((j["hip"], j["lk"], back), (j["lk"], j["lf"], back), (j["sh"], j["le"], back), (j["le"], j["lh"], back)):
        c.drawLine(*a, *b, cc)
    c.drawLine(*j["hip"], *j["neck"], ink)
    # accent "shirt" stripe on torso for character identity
    acc = paint(actor.accent, w * 0.55)
    c.drawLine(lerp(j["hip"][0], j["neck"][0], 0.25), lerp(j["hip"][1], j["neck"][1], 0.25),
               lerp(j["hip"][0], j["neck"][0], 0.75), lerp(j["hip"][1], j["neck"][1], 0.75), acc)
    for a, b in ((j["hip"], j["rk"]), (j["rk"], j["rf"]), (j["sh"], j["re"]), (j["re"], j["rh"])):
        c.drawLine(*a, *b, ink)
    hx, hy = j["head"]
    r = L["head"] * actor.scale
    c.drawCircle(hx, hy, r, paint((255, 255, 255), fill=True))
    c.drawCircle(hx, hy, r, paint(actor.color, w * 0.8))
    draw_face(c, actor, j, t, talking)
    draw_hat(c, actor, j, r)
    if actor.prop:
        draw_hand_prop(c, actor, j, t)
    if actor.stars:
        x0 = min(max(hx - 160, 40), W - 40 - 5 * 64)
        for i in range(6):
            cx = x0 + i * 64
            on = i < actor.stars
            star(c, cx, hy - r - 70, 26, (255, 221, 51) if on and int(t * 4) % 2 == 0 else ((255, 255, 255) if on else (90, 90, 90)),
                 outline=(20, 20, 28))
    return j


def draw_hat(c, actor, j, r):
    hx, hy = j["head"]
    f = actor.facing
    if actor.hat == "cap":
        c.save()
        c.clipRect(skia.Rect.MakeXYWH(hx - r - 20, hy - r - 20, 2 * r + 40, r * 0.62 + 20))
        c.drawCircle(hx, hy, r + 3, paint(actor.accent, fill=True))
        c.restore()
        c.drawRoundRect(skia.Rect.MakeXYWH(hx - r * 0.2 if f > 0 else hx - r * 1.3, hy - r * 0.48, r * 1.5, r * 0.22), 8, 8,
                        paint(actor.accent, fill=True))
    elif actor.hat == "tophat":
        c.drawRect(skia.Rect.MakeXYWH(hx - r * 0.65, hy - r * 2.1, r * 1.3, r * 1.25), paint((20, 20, 28), fill=True))
        c.drawRect(skia.Rect.MakeXYWH(hx - r * 1.05, hy - r * 0.92, r * 2.1, 12), paint((20, 20, 28), fill=True))
        c.drawRect(skia.Rect.MakeXYWH(hx - r * 0.65, hy - r * 1.2, r * 1.3, 10), paint(actor.accent, fill=True))
    elif actor.hat == "police":
        c.drawRoundRect(skia.Rect.MakeXYWH(hx - r * 0.95, hy - r * 1.25, r * 1.9, r * 0.75), 10, 10, paint((25, 40, 110), fill=True))
        c.drawRect(skia.Rect.MakeXYWH(hx - r * 1.1, hy - r * 0.6, r * 2.2, 11), paint((15, 20, 60), fill=True))
        star(c, hx, hy - r * 0.9, 11, (255, 210, 60))
    elif actor.hat == "crown":
        p = skia.Path()
        p.moveTo(hx - r * 0.8, hy - r * 0.8)
        for i, dx in enumerate((-0.8, -0.4, 0, 0.4, 0.8)):
            p.lineTo(hx + r * dx, hy - r * (1.65 if i % 2 == 0 else 1.15))
        p.lineTo(hx + r * 0.8, hy - r * 0.8)
        p.close()
        c.drawPath(p, paint((255, 205, 40), fill=True))
    elif actor.hat == "headset":
        c.drawArc(skia.Rect.MakeXYWH(hx - r * 1.08, hy - r * 1.08, r * 2.16, r * 2.16), 190, 160, False, paint((30, 30, 30), 9))
        c.drawRoundRect(skia.Rect.MakeXYWH(hx - r * 1.2, hy - 16, 18, 34), 8, 8, paint(actor.accent, fill=True))
    elif actor.hat == "sunglasses":
        f = actor.facing
        ex = hx + f * r * 0.3
        c.drawRoundRect(skia.Rect.MakeXYWH(ex - 34, hy - r * 0.3, 68, 20), 8, 8, paint((15, 15, 20), fill=True))


def draw_hand_prop(c, actor, j, t):
    hx, hy = j["rh"]
    if actor.prop == "phone":
        c.save()
        c.translate(hx, hy - 10)
        c.rotate(-15 * actor.facing)
        c.drawRoundRect(skia.Rect.MakeXYWH(-20, -36, 40, 70), 8, 8, paint((25, 25, 35), fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(-15, -30, 30, 56), 4, 4, paint((80, 200, 255), fill=True))
        c.restore()
    elif actor.prop == "money":
        for i in range(3):
            c.save()
            c.translate(hx + i * 6, hy - i * 5)
            c.rotate(-10 + 12 * math.sin(t * 6 + i))
            c.drawRoundRect(skia.Rect.MakeXYWH(-34, -18, 68, 36), 4, 4, paint((80, 190, 90), fill=True))
            c.drawCircle(0, 0, 9, paint((40, 120, 50), 3))
            c.restore()
    elif actor.prop == "controller":
        c.drawRoundRect(skia.Rect.MakeXYWH(hx - 40, hy - 22, 80, 44), 20, 20, paint((40, 40, 50), fill=True))
        c.drawCircle(hx + 18, hy - 4, 6, paint((255, 80, 80), fill=True))
        c.drawCircle(hx - 18, hy, 7, paint((150, 150, 160), fill=True))
    elif actor.prop == "trophy":
        c.drawRect(skia.Rect.MakeXYWH(hx - 10, hy - 10, 20, 30), paint((220, 170, 30), fill=True))
        c.drawOval(skia.Rect.MakeXYWH(hx - 30, hy - 70, 60, 64), paint((255, 205, 40), fill=True))
    elif actor.prop == "mic":
        c.drawLine(hx, hy, hx + 8 * actor.facing, hy - 40, paint((40, 40, 50), 10))
        c.drawCircle(hx + 10 * actor.facing, hy - 50, 15, paint((90, 90, 100), fill=True))


def star(c, cx, cy, r, color, outline=None):
    p = skia.Path()
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = -math.pi / 2 + i * math.pi / 5
        (p.moveTo if i == 0 else p.lineTo)(cx + rr * math.cos(a), cy + rr * math.sin(a))
    p.close()
    c.drawPath(p, paint(color, fill=True))
    if outline:
        c.drawPath(p, paint(outline, 3))


# --------------------------------------------------------------- props in the world
def draw_car(c, x, y, color, t, moving, police=False, facing=1, driver=None, world_t=0):
    c.save()
    c.translate(x, y)
    c.scale(facing * 1.35, 1.35)
    bounce = 3 * math.sin(t * 20) if moving else 0
    c.translate(0, bounce)
    body = skia.Path()
    body.moveTo(-190, -40)
    body.lineTo(-180, -95)
    body.quadTo(-170, -110, -140, -110)
    body.lineTo(-80, -112)
    body.lineTo(-40, -175)
    body.lineTo(70, -175)
    body.lineTo(120, -112)
    body.lineTo(175, -105)
    body.quadTo(200, -100, 200, -70)
    body.lineTo(200, -40)
    body.close()
    col = (240, 240, 245) if police else color
    c.drawPath(body, paint(col, fill=True))
    c.drawPath(body, paint((20, 20, 28), 7))
    if police:
        c.drawRect(skia.Rect.MakeXYWH(-190, -80, 390, 26), paint((25, 40, 110), fill=True))
        on = int(world_t * 6) % 2 == 0
        c.drawRoundRect(skia.Rect.MakeXYWH(-20, -200, 34, 24), 6, 6, paint((255, 40, 40) if on else (120, 20, 20), fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(16, -200, 34, 24), 6, 6, paint((40, 90, 255) if not on else (20, 30, 120), fill=True))
    win = skia.Path()
    win.moveTo(-60, -112)
    win.lineTo(-28, -162)
    win.lineTo(60, -162)
    win.lineTo(98, -112)
    win.close()
    c.drawPath(win, paint((170, 225, 255), fill=True))
    c.drawPath(win, paint((20, 20, 28), 5))
    c.drawLine(18, -162, 18, -112, paint((20, 20, 28), 5))
    for wx in (-120, 125):
        c.save()
        c.translate(wx, -40)
        c.rotate((t * 900) % 360 if moving else 0)
        c.drawCircle(0, 0, 38, paint((25, 25, 30), fill=True))
        c.drawCircle(0, 0, 17, paint((190, 190, 200), fill=True))
        c.drawLine(-15, 0, 15, 0, paint((90, 90, 100), 5))
        c.restore()
    c.drawCircle(185, -82, 9, paint((255, 240, 150), fill=True))
    if driver:  # head of the driver in the window
        c.drawCircle(-5, -140, 26, paint((255, 255, 255), fill=True))
        c.drawCircle(-5, -140, 26, paint((20, 20, 28), 7))
        c.drawCircle(6, -144, 4, paint((20, 20, 28), fill=True))
    c.restore()


def draw_world_prop(c, pr, t, wt):
    kind = pr.get("kind")
    x = pr["_x"]
    if kind in ("car", "police_car", "sports_car"):
        draw_car(c, x, GROUND + 8, tuple(int(pr.get("color", "#ff2e63").lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)),
                 t, pr.get("_moving", False), police=kind == "police_car", facing=pr.get("facing", 1),
                 driver=pr.get("driver"), world_t=wt)
    elif kind == "sign":
        y = GROUND - 330
        c.drawLine(x, GROUND, x, y + 100, paint((90, 70, 50), 14))
        c.drawRoundRect(skia.Rect.MakeXYWH(x - 180, y - 40, 360, 150), 18, 18, paint(pr.get("color", "#ffffff"), fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(x - 180, y - 40, 360, 150), 18, 18, paint((20, 20, 28), 7))
        draw_text_center(c, pr.get("text", ""), x, y + 35, 60, (20, 20, 28), 320)
    elif kind == "tv":  # wall screen high above the actors' heads
        y = GROUND - 1010
        c.drawRoundRect(skia.Rect.MakeXYWH(x - 300, y, 600, 340), 24, 24, paint((25, 25, 35), fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(x - 280, y + 20, 560, 300), 14, 14, paint(pr.get("color", "#28c8ff"), fill=True))
        on = int(t * 2) % 2 == 0
        c.drawCircle(x - 240, y + 55, 12, paint((255, 40, 40) if on else (120, 20, 20), fill=True))
        draw_text_center(c, pr.get("text", ""), x, y + 170, 72, (255, 255, 255), 500, stroke=True)
    elif kind == "chart":
        vals = pr.get("values", [3, 5, 9])
        labels = pr.get("labels", [""] * len(vals))
        k = ease_out(t / 1.4)
        base = GROUND - 40
        mx = max(vals) or 1
        n = len(vals)
        bw = 110
        x0 = x - (n * (bw + 30)) / 2
        for i, v in enumerate(vals):
            h = 520 * v / mx * ease_out((t - i * 0.25) / 1.0) if t > i * 0.25 else 0
            col = (255, 46, 99) if i == n - 1 else (0, 200, 255)
            c.drawRoundRect(skia.Rect.MakeXYWH(x0 + i * (bw + 30), base - h, bw, h), 12, 12, paint(col, fill=True))
            c.drawRoundRect(skia.Rect.MakeXYWH(x0 + i * (bw + 30), base - h, bw, h), 12, 12, paint((20, 20, 28), 6))
            if labels[i]:
                draw_text_center(c, str(labels[i]), x0 + i * (bw + 30) + bw / 2, base - h - 40, 46, (255, 255, 255), 200, stroke=True)
    elif kind == "money_rain":
        rnd = random.Random(7)
        for i in range(26):
            mx = rnd.uniform(0, W)
            my = (rnd.uniform(-400, 1400) + t * rnd.uniform(250, 420)) % 1500 + 150
            c.save()
            c.translate(mx, my)
            c.rotate(math.degrees(math.sin(t * 3 + i)) * 0.6)
            c.drawRoundRect(skia.Rect.MakeXYWH(-38, -20, 76, 40), 4, 4, paint((90, 200, 100), fill=True))
            c.drawCircle(0, 0, 10, paint((40, 120, 50), 3))
            c.restore()
    elif kind == "palm":
        draw_palm(c, x, GROUND, pr.get("scale", 1.0), t)
    elif kind == "building":
        bw, bh = pr.get("w", 260), pr.get("h", 700)
        c.drawRect(skia.Rect.MakeXYWH(x - bw / 2, GROUND - bh, bw, bh), paint(pr.get("color", "#3a2a6a"), fill=True))
        for wy in range(int(GROUND - bh + 30), GROUND - 60, 70):
            for wx in range(int(x - bw / 2 + 25), int(x + bw / 2 - 40), 60):
                c.drawRect(skia.Rect.MakeXYWH(wx, wy, 34, 40), paint((255, 220, 120), fill=True))


def draw_palm(c, x, base, s, t):
    sway = 4 * math.sin(t * 1.3)
    trunk = skia.Path()
    trunk.moveTo(x - 14 * s, base)
    trunk.quadTo(x + 30 * s, base - 300 * s, x + (20 + sway) * s, base - 560 * s)
    trunk.lineTo(x + (36 + sway) * s, base - 556 * s)
    trunk.quadTo(x + 50 * s, base - 300 * s, x + 14 * s, base)
    trunk.close()
    c.drawPath(trunk, paint((60, 30, 70), fill=True))
    top = (x + (28 + sway) * s, base - 560 * s)
    for k in range(7):
        a = math.radians(-170 + k * 27 + 3 * math.sin(t * 1.6 + k))
        L_ = 240 * s
        ex, ey = top[0] + L_ * math.cos(a), top[1] + L_ * math.sin(a) * 0.55 + 90 * s
        mx, my = top[0] + L_ * 0.5 * math.cos(a), top[1] - 50 * s
        fr = skia.Path()
        fr.moveTo(*top)
        fr.quadTo(mx, my - 26 * s, ex, ey)
        fr.quadTo(mx, my + 26 * s, top[0], top[1] + 10 * s)
        c.drawPath(fr, paint((40, 140, 90), fill=True))


def draw_text_center(c, text, x, y, size, color, max_w, stroke=False):
    font = skia.Font(typeface(), size)
    lines = wrap_text(str(text).upper(), font, max_w)
    lh = size * 1.05
    y0 = y - (len(lines) - 1) * lh / 2 + size * 0.35
    for i, ln in enumerate(lines):
        w = font.measureText(ln)
        if stroke:
            c.drawString(ln, x - w / 2, y0 + i * lh, font, paint((20, 20, 28), size * 0.14))
        c.drawString(ln, x - w / 2, y0 + i * lh, font, paint(color, fill=True))


# --------------------------------------------------------------- settings (backgrounds)
SETTINGS = {}


def setting(name):
    def deco(fn):
        SETTINGS[name] = fn
        return fn
    return deco


def _grad(c, top, bottom, y0=0, y1=GROUND):
    p = skia.Paint(Shader=skia.GradientShader.MakeLinear([(0, y0), (0, y1)], [rgb(top), rgb(bottom)]))
    c.drawRect(skia.Rect.MakeXYWH(-400, y0 - 400, W + 800, y1 - y0 + 400), p)


@setting("city_night")
def _city_night(c, t, cam):
    _grad(c, (25, 10, 60), (255, 70, 140))
    c.drawCircle(540 - cam * 0.2, 800, 230, paint((255, 190, 80), fill=True, alpha=235))
    rnd = random.Random(3)
    x = -300
    while x < W + 300:
        bw, bh = rnd.randint(110, 220), rnd.randint(250, 640)
        xx = x - cam * 0.4
        c.drawRect(skia.Rect.MakeXYWH(xx, GROUND - bh, bw, bh), paint((45, 18, 80), fill=True))
        for wy in range(GROUND - bh + 25, GROUND - 40, 55):
            for wx in range(int(xx) + 18, int(xx) + bw - 30, 40):
                if rnd.random() < 0.35:
                    c.drawRect(skia.Rect.MakeXYWH(wx, wy, 18, 26), paint(rnd.choice([(255, 220, 90), (255, 90, 180), (0, 230, 255)]), fill=True))
        x += bw + rnd.randint(10, 40)
    draw_palm(c, 120 - cam * 0.7, GROUND, 1.0, t)
    draw_palm(c, 930 - cam * 0.7, GROUND, 0.85, t + 1)
    _ground(c, (30, 12, 50), (255, 46, 160))


@setting("city_day")
def _city_day(c, t, cam):
    _grad(c, (110, 190, 255), (210, 240, 255))
    rnd = random.Random(5)
    for i in range(5):
        cx = (i * 300 + t * 20 - cam * 0.1) % (W + 400) - 200
        c.drawOval(skia.Rect.MakeXYWH(cx, 300 + i * 60 % 200, 230, 70), paint((255, 255, 255), fill=True))
    x = -300
    while x < W + 300:
        bw, bh = rnd.randint(120, 230), rnd.randint(300, 700)
        col = rnd.choice([(120, 150, 200), (150, 170, 210), (100, 130, 180)])
        c.drawRect(skia.Rect.MakeXYWH(x - cam * 0.4, GROUND - bh, bw, bh), paint(col, fill=True))
        x += bw + rnd.randint(8, 30)
    _ground(c, (120, 120, 130), (240, 240, 240))


@setting("beach")
def _beach(c, t, cam):
    _grad(c, (255, 150, 90), (255, 220, 150))
    c.drawCircle(540, 900, 200, paint((255, 240, 180), fill=True))
    c.drawRect(skia.Rect.MakeXYWH(-400, 980, W + 800, GROUND - 980), paint((30, 150, 200), fill=True))
    for i in range(6):
        y = 1010 + i * 40
        off = math.sin(t * 2 + i) * 30
        c.drawLine(-100 + off, y, W + 100 + off, y, paint((120, 210, 240), 4, alpha=150))
    draw_palm(c, 140 - cam * 0.6, GROUND, 1.05, t)
    draw_palm(c, 960 - cam * 0.6, GROUND, 0.9, t + 2)
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, H), paint((240, 210, 150), fill=True))


@setting("room")
def _room(c, t, cam):
    c.drawRect(skia.Rect.MakeXYWH(-400, -400, W + 800, GROUND + 400), paint((250, 232, 200), fill=True))
    c.drawRoundRect(skia.Rect.MakeXYWH(660 - cam * 0.3, 420, 300, 330), 10, 10, paint((150, 210, 250), fill=True))
    c.drawRoundRect(skia.Rect.MakeXYWH(660 - cam * 0.3, 420, 300, 330), 10, 10, paint((120, 90, 70), 14))
    c.drawLine(810 - cam * 0.3, 420, 810 - cam * 0.3, 750, paint((120, 90, 70), 10))
    c.drawRoundRect(skia.Rect.MakeXYWH(80 - cam * 0.5, 560, 220, 150), 8, 8, paint((255, 120, 120), fill=True))
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, H), paint((170, 120, 85), fill=True))
    for i in range(-4, 14):
        c.drawLine(i * 120 - cam * 0.8, GROUND, i * 120 - cam * 0.8 - 60, H, paint((140, 95, 65), 4))


@setting("stage")
def _stage(c, t, cam):
    c.drawRect(skia.Rect.MakeXYWH(-400, -400, W + 800, H + 800), paint((28, 20, 50), fill=True))
    sp = skia.Paint(Shader=skia.GradientShader.MakeRadial((540, GROUND - 200), 700,
                                                           [rgb((255, 230, 160), 120), rgb((255, 230, 160), 0)]))
    c.drawRect(skia.Rect.MakeXYWH(-400, -400, W + 800, H + 800), sp)
    _ground(c, (60, 30, 70), (255, 180, 60))


@setting("news_desk")
def _news(c, t, cam):
    _grad(c, (10, 30, 80), (20, 80, 170))
    for i in range(12):
        c.drawLine(-200 + i * 120 - cam * 0.2, 200, -500 + i * 160 - cam * 0.2, GROUND, paint((60, 120, 220), 3, alpha=90))
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND - 330, W + 800, 60), paint((200, 16, 40), fill=True))
    draw_text_center(c, "BREAKING NEWS", 300, GROUND - 300, 46, (255, 255, 255), 600)
    _ground(c, (8, 20, 55), (80, 180, 255))


@setting("void")
def _void(c, t, cam):
    c.drawRect(skia.Rect.MakeXYWH(-400, -400, W + 800, H + 800), paint((245, 245, 240), fill=True))
    c.drawLine(-400, GROUND, W + 400, GROUND, paint((20, 20, 28), 6))


@setting("gaming")
def _gaming(c, t, cam):
    _grad(c, (15, 10, 35), (60, 20, 110))
    for i in range(18):
        y = GROUND + (i * 40 + t * 120) % 700
        c.drawLine(-400, y, W + 400, y, paint((140, 60, 255), 3, alpha=140))
    for i in range(-10, 11):
        c.drawLine(540 + i * 40, GROUND, 540 + i * 220, H, paint((140, 60, 255), 3, alpha=140))
    for i in range(14):
        x = (i * 97 + t * 30) % W
        c.drawRect(skia.Rect.MakeXYWH(x, 300 + (i * 131) % 700, 14, 14), paint((0, 230, 255), fill=True, alpha=120))
    c.drawLine(-400, GROUND, W + 400, GROUND, paint((0, 230, 255), 6))


def _ground(c, fill, line):
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, H), paint(fill, fill=True))
    lighter = tuple(min(255, v + 28) for v in fill)
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, 70), paint(lighter, fill=True))
    for i in range(-6, 16):
        c.drawLine(i * 110, GROUND, i * 110 - 30, GROUND + 70, paint(fill, 4))
    c.drawLine(-400, GROUND, W + 400, GROUND, paint(line, 6))
    c.drawLine(-400, GROUND + 70, W + 400, GROUND + 70, paint(tuple(max(0, v - 10) for v in fill), 8))


# --------------------------------------------------------------- effects
def fx_layer(c, names, t, actors_j):
    if "speed_lines" in names:
        rnd = random.Random(int(t * 12))
        for _ in range(16):
            y = rnd.uniform(300, GROUND)
            x = rnd.uniform(0, W)
            c.drawLine(x, y, x + rnd.uniform(120, 300), y, paint((255, 255, 255), 5, alpha=170))
    if "impact" in names and actors_j:
        j = list(actors_j.values())[-1]
        cx, cy = j["head"]
        k = (t * 3) % 1
        for i in range(12):
            a = i * math.pi / 6
            r0, r1 = 70 + 60 * k, 130 + 90 * k
            c.drawLine(cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a), cy + r1 * math.sin(a),
                       paint((255, 221, 51), 10, alpha=int(255 * (1 - k))))
    if "sweat" in names and actors_j:
        for j in actors_j.values():
            hx, hy = j["head"]
            k = (t * 1.5) % 1
            p = skia.Path()
            x, y = hx + 55, hy - 30 + 60 * k
            p.moveTo(x, y - 18)
            p.quadTo(x + 14, y, x, y + 10)
            p.quadTo(x - 14, y, x, y - 18)
            c.drawPath(p, paint((120, 200, 255), fill=True, alpha=int(255 * (1 - k))))
    if "hearts" in names:
        for i in range(8):
            k = (t * 0.6 + i / 8) % 1
            x = 200 + i * 90 + 30 * math.sin(t * 2 + i)
            y = GROUND - 200 - k * 800
            heart(c, x, y, 26, (255, 70, 120), alpha=int(255 * (1 - k)))
    if "exclaim" in names and actors_j:
        for j in actors_j.values():
            hx, hy = j["head"]
            s = ease_back(min(1, t / 0.25))
            draw_text_center(c, "!", hx + 70, hy - 110, int(120 * s) + 1, (255, 221, 51), 200, stroke=True)
            break


def heart(c, x, y, r, color, alpha=255):
    p = skia.Path()
    p.moveTo(x, y + r)
    p.cubicTo(x - 2 * r, y - 0.2 * r, x - r, y - 1.4 * r, x, y - 0.5 * r)
    p.cubicTo(x + r, y - 1.4 * r, x + 2 * r, y - 0.2 * r, x, y + r)
    c.drawPath(p, paint(color, fill=True, alpha=alpha))


def overlay_fx(c, names, t):
    if "police_lights" in names:
        on = int(t * 5) % 2 == 0
        col = (255, 30, 60) if on else (30, 90, 255)
        sp = skia.Paint(Shader=skia.GradientShader.MakeRadial((0 if on else W, 300), 1100,
                                                               [rgb(col, 110), rgb(col, 0)]))
        c.drawRect(skia.Rect.MakeXYWH(0, 0, W, H), sp)
    if "vignette" in names:
        sp = skia.Paint(Shader=skia.GradientShader.MakeRadial((W / 2, H / 2), 1150, [rgb((0, 0, 0), 0), rgb((0, 0, 0), 150)]))
        c.drawRect(skia.Rect.MakeXYWH(0, 0, W, H), sp)


def speech_bubble(c, text, ax, ay, t, thought=False):
    s = ease_back(min(1, t / 0.25))
    if s <= 0.02:
        return
    font = skia.Font(typeface(), 64)
    lines = wrap_text(text.upper(), font, 620)
    lh = 70
    bw = max(font.measureText(l) for l in lines) + 70
    bh = lh * len(lines) + 50
    bx = min(max(40, ax - bw / 2), W - 40 - bw)
    by = max(380, ay - 190 - bh)
    c.save()
    c.translate(ax, ay - 120)
    c.scale(s, s)
    c.translate(-ax, -(ay - 120))
    fillp, inkp = paint((255, 255, 255), fill=True), paint((20, 20, 28), 7)
    tail = skia.Path()
    tail.moveTo(ax - 20, by + bh - 5)
    tail.lineTo(ax + 5, ay - 120)
    tail.lineTo(ax + 25, by + bh - 5)
    tail.close()
    rect = skia.Rect.MakeXYWH(bx, by, bw, bh)
    if thought:
        c.drawRoundRect(rect, bh / 2, bh / 2, fillp)
        c.drawRoundRect(rect, bh / 2, bh / 2, inkp)
        for i, r in enumerate((16, 11)):
            c.drawCircle(ax + 10, by + bh + 25 + i * 30, r, fillp)
            c.drawCircle(ax + 10, by + bh + 25 + i * 30, r, inkp)
    else:
        c.drawPath(tail, fillp)
        c.drawPath(tail, inkp)
        c.drawRoundRect(rect, 34, 34, fillp)
        c.drawRoundRect(rect, 34, 34, inkp)
        c.drawRect(skia.Rect.MakeXYWH(ax - 16, by + bh - 12, 38, 14), fillp)
    for i, ln in enumerate(lines):
        w = font.measureText(ln)
        c.drawString(ln, bx + (bw - w) / 2, by + 30 + lh * (i + 0.8), font, paint((20, 20, 28), fill=True))
    c.restore()


# --------------------------------------------------------------- the world (keeps state across scenes)
ACCENTS = [(255, 46, 99), (0, 200, 255), (255, 170, 20), (90, 200, 90), (170, 90, 255)]


class World:
    def __init__(self):
        self.actors: dict[str, Actor] = {}
        self.scene_id = None
        self.scene_start_x = {}
        self.blend_from = {}

    def _setup_scene(self, sc, key):
        self.scene_id = key
        self.scene_start_x = {}
        self.blend_from = {}
        for i, a in enumerate(sc.get("actors", [])):
            aid = str(a.get("id", f"a{i}"))
            act = self.actors.get(aid)
            if act is None:
                act = Actor(id=aid, accent=ACCENTS[len(self.actors) % len(ACCENTS)])
                act.x = W * float(a.get("x", 0.5))
                self.actors[aid] = act
            elif "x" in a:  # omit "x" to continue from where the actor ended last scene
                act.x = W * float(a["x"])
            if a.get("color"):
                act.accent = tuple(int(a["color"].lstrip("#")[k:k + 2], 16) for k in (0, 2, 4))
            act.hat = a.get("hat", act.hat)
            act.face = a.get("face", "happy" if a.get("action") in ("celebrate", "dance", "cheer") else
                             "shock" if a.get("action") in ("shocked", "shock") else
                             "sad" if a.get("action") == "sad" else a.get("face", "neutral"))
            act.prop = a.get("prop", "")
            act.scale = float(a.get("scale", act.scale))
            act.stars = int(a.get("stars", 0))
            if "facing" in a:
                act.facing = int(a["facing"])
            self.scene_start_x[aid] = act.x
            self.blend_from[aid] = dict(act.last_pose)
        self.visible = {str(a.get("id", f"a{i}")) for i, a in enumerate(sc.get("actors", []))}
        for pr in sc.get("props", []):
            pr["_x0"] = W * float(pr.get("x", 0.5))
            pr["_x"] = pr["_x0"]

    def frame(self, sc, lt, dur, scene_key):
        if scene_key != self.scene_id:
            self._setup_scene(sc, scene_key)
        surface = skia.Surface(W, H)
        c = surface.getCanvas()
        # camera
        cam = sc.get("camera", "")
        zoom, pan, shake = 1.0, 0.0, (0, 0)
        if cam == "zoom_in":
            zoom = lerp(1.0, 1.18, ease(lt / max(dur, 0.1)))
        elif cam == "zoom_out":
            zoom = lerp(1.2, 1.0, ease(lt / max(dur, 0.1)))
        elif cam == "punch":
            zoom = 1 + 0.12 * math.exp(-lt * 6)
        elif cam == "pan":
            pan = lerp(-60, 60, ease(lt / max(dur, 0.1)))
        if cam == "shake" or "impact" in sc.get("fx", []):
            amp = 14 * math.exp(-lt * 3)
            shake = (amp * math.sin(lt * 70), amp * math.cos(lt * 63))
        c.save()
        c.translate(W / 2 + shake[0], GROUND - 300 + shake[1])
        c.scale(zoom, zoom)
        c.translate(-W / 2 - pan, -(GROUND - 300))
        SETTINGS.get(sc.get("setting", "city_night"), _city_night)(c, lt, pan)
        if sc.get("setting", "city_night") not in ("void",):  # haze so characters read clearly
            c.drawRect(skia.Rect.MakeXYWH(-400, -400, W + 800, GROUND + 400), paint((20, 10, 40), fill=True, alpha=60))
        # props
        for pr in sc.get("props", []):
            if "move_to" in pr:
                k = ease(lt / max(0.1, float(pr.get("move_time", dur))))
                pr["_x"] = lerp(pr["_x0"], W * float(pr["move_to"]), k)
                pr["_moving"] = 0 < k < 1
                pr["facing"] = 1 if pr["move_to"] >= pr.get("x", 0.5) else -1
            if pr.get("kind") not in ("money_rain",):
                draw_world_prop(c, pr, lt, lt)
        # actors
        joints = {}
        speaker = sc.get("speaker")
        for i, a in enumerate(sc.get("actors", [])):
            aid = str(a.get("id", f"a{i}"))
            act = self.actors[aid]
            action = a.get("action", "idle")
            # movement
            if "to" in a:
                x0, x1 = self.scene_start_x[aid], W * float(a["to"])
                speed = MOVING.get(action, 300)
                travel = abs(x1 - x0) / speed
                k = min(1, lt / max(0.1, travel))
                act.x = lerp(x0, x1, k)
                if abs(x1 - x0) > 3:
                    act.facing = 1 if x1 > x0 else -1
                if k >= 1 and action in MOVING:
                    action = a.get("then", "idle")
            target = act_pose(action, lt, act)
            k = ease(lt / 0.25)
            p = blend(self.blend_from[aid], target, k) if k < 1 else target
            act.last_pose = p
            talking = speaker == aid and bool(sc.get("say"))
            joints[aid] = draw_actor(c, act, p, lt, talking=talking)
        fx_layer(c, sc.get("fx", []), lt, joints)
        for pr in sc.get("props", []):
            if pr.get("kind") == "money_rain":
                draw_world_prop(c, pr, lt, lt)
        b = sc.get("bubble")
        if b and b.get("text") and str(b.get("actor")) in joints:
            j = joints[str(b["actor"])]
            speech_bubble(c, b["text"], j["head"][0], j["head"][1], lt - float(b.get("at", 0.15)), thought=b.get("thought", False))
        c.restore()
        overlay_fx(c, sc.get("fx", []), lt)
        if sc.get("title"):
            s = ease_back(min(1, lt / 0.3))
            c.save()
            c.translate(W / 2, 300)
            c.scale(s, s)
            draw_text_center(c, sc["title"], 0, 0, 104, (255, 255, 255), 940, stroke=True)
            c.restore()
        img = surface.makeImageSnapshot()
        arr = img.toarray(colorType=skia.kRGBA_8888_ColorType)[:, :, :3]
        return arr
