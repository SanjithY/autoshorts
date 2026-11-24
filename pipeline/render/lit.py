"""'Lit set' stickman style: flat 2D stickmen living inside a rich, lit, painted-3D world.

Characters: white heads with a heavy outline, single black line limbs with round ends, white circle hands,
black oval shoes, one flat clothing shape per character with a thin darker edge on the shadow side.
World: perspective floors/ground converging on a vanishing point, furniture and buildings with a light side,
a dark side and a top face, soft cast shadows, warm key light from one side and cool purple shadow from the
other, glow around lamps/windows, haze in the distance, a blurred foreground object, a dark vignette.
Camera: never still; slow push-ins, glides that follow the action, a punch-in on key words, and a whip-slide
between scenes instead of hard cuts.

The palette and sets come from the script, so every topic gets its own look.
"""
from __future__ import annotations

import math
import random

import numpy as np
import skia

from .stick import BASE, MOVING, act_pose, auto_steps, blend, ease, lerp

W, H = 1080, 1920
HORIZON = 1130          # eye line for exteriors
WALL_BASE = 1180        # where back wall meets floor in interiors
FLOOR = 1640            # feet of near characters
INK = (23, 23, 28)


def hexc(s, default=(200, 200, 200)):
    if isinstance(s, (tuple, list)):
        return tuple(s)
    try:
        s = s.lstrip("#")
        return tuple(int(s[k:k + 2], 16) for k in (0, 2, 4))
    except Exception:
        return default


def rgb(c, a=255):
    return skia.Color(int(c[0]), int(c[1]), int(c[2]), int(a))


def mix(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def P(color, width=0, fill=False, alpha=255, cap=True):
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


def blurred(p, sigma):
    p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, sigma))
    return p


def poly(c, pts, paint):
    path = skia.Path()
    path.moveTo(*pts[0])
    for q in pts[1:]:
        path.lineTo(*q)
    path.close()
    c.drawPath(path, paint)
    return path


def vgrad(c, x, y, w, h, top, bottom, alpha=255):
    c.drawRect(skia.Rect.MakeXYWH(x, y, w, h), skia.Paint(Shader=skia.GradientShader.MakeLinear(
        [(0, y), (0, y + h)], [rgb(top, alpha), rgb(bottom, alpha)])))


# --------------------------------------------------------------- light
LIGHTS = {  # sky top, sky bottom, key light colour, shadow colour, ambient tint
    "golden": ((122, 150, 205), (246, 200, 140), (255, 214, 150), (74, 59, 120)),
    "sunset": ((70, 60, 130), (240, 138, 75), (255, 170, 110), (60, 40, 100)),
    "day": ((95, 160, 230), (205, 228, 245), (255, 245, 220), (80, 90, 140)),
    "warm": ((60, 45, 50), (120, 85, 60), (255, 205, 140), (74, 59, 120)),
    "cold": ((40, 52, 80), (90, 105, 130), (190, 210, 255), (38, 53, 94)),
    "night": ((14, 18, 46), (50, 50, 100), (255, 210, 150), (30, 30, 80)),
    "storm": ((45, 50, 70), (110, 115, 130), (220, 225, 240), (40, 45, 70)),
    "dust": ((170, 140, 110), (235, 195, 140), (255, 210, 150), (110, 80, 90)),
}


class Light:
    def __init__(self, name="golden", side=-1):
        self.name = name if name in LIGHTS else "golden"
        self.sky0, self.sky1, self.key, self.shadow = LIGHTS[self.name]
        self.side = side  # -1: light comes from the left, 1: from the right

    def lit(self, col, k=0.35):
        return mix(col, self.key, k)

    def dark(self, col, k=0.4):
        return mix(col, self.shadow, k)

    def shadow_dx(self):
        return -self.side  # shadows fall away from the light


def cast_shadow(c, lt, x, y, w, h=26, length=1.0, alpha=110):
    """Soft cast shadow on the floor/ground, stretched away from the light."""
    p = blurred(P(lt.shadow, fill=True, alpha=alpha), 10)
    dx = lt.shadow_dx() * w * 0.35 * length
    c.drawOval(skia.Rect.MakeXYWH(x - w / 2 + dx, y - h / 2, w + abs(dx) * 0.6, h), p)


def box3d(c, lt, x, base, w, h, d, col, vp, outline=True):
    """A box whose front face sits at (x-w/2..x+w/2, base-h..base) with depth toward the vanishing point.
    Draws the side face (dark or lit by light side), the top face (lightest) and the front face."""
    fx0, fx1, fy0, fy1 = x - w / 2, x + w / 2, base - h, base
    k = d / 900.0
    back = lambda q: (q[0] + (vp[0] - q[0]) * k, q[1] + (vp[1] - q[1]) * k)
    top = [(fx0, fy0), (fx1, fy0), back((fx1, fy0)), back((fx0, fy0))]
    if x < vp[0]:  # we see the right side
        side = [(fx1, fy0), (fx1, fy1), back((fx1, fy1)), back((fx1, fy0))]
        side_col = lt.lit(col, 0.25) if lt.side > 0 else lt.dark(col, 0.45)
    else:
        side = [(fx0, fy0), (fx0, fy1), back((fx0, fy1)), back((fx0, fy0))]
        side_col = lt.lit(col, 0.25) if lt.side < 0 else lt.dark(col, 0.45)
    ol = P(INK, 3, alpha=150)
    poly(c, side, P(side_col, fill=True))
    if fy0 > vp[1]:  # top only visible when it's below eye level
        poly(c, top, P(lt.lit(col, 0.45), fill=True))
        if outline:
            poly(c, top, ol)
    front = skia.Rect.MakeLTRB(fx0, fy0, fx1, fy1)
    c.drawRect(front, skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
        [(fx0 if lt.side < 0 else fx1, 0), (fx1 if lt.side < 0 else fx0, 0)],
        [rgb(lt.lit(col, 0.2)), rgb(lt.dark(col, 0.18))])))
    if outline:
        poly(c, side, ol)
        c.drawRect(front, ol)
    return front


def glow(c, x, y, r, col, alpha=150):
    c.drawCircle(x, y, r, skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeRadial(
        (x, y), r, [rgb(col, alpha), rgb(col, 0)])))


# --------------------------------------------------------------- items (shared by sets)
def item(c, lt, name, x, base, s, vp, t, col=None):
    """Draw one set item standing on `base` at horizontal `x`, scale s (1 = near)."""
    rnd = random.Random(int(x * 7 + base))
    g = lambda v: v * s
    if name == "desk":
        cc = col or (120, 78, 50)
        box3d(c, lt, x, base - g(150), g(420), g(26), g(160), cc, vp)
        for dx in (-185, 185):
            box3d(c, lt, x + g(dx), base, g(22), g(150), g(140), lt.dark(cc, 0.2), vp)
        box3d(c, lt, x + g(110), base, g(150), g(130), g(120), cc, vp)
        cast_shadow(c, lt, x, base, g(460), g(40))
    elif name == "typewriter":
        box3d(c, lt, x, base, g(120), g(46), g(70), (60, 60, 70), vp)
        for i in range(3):
            c.drawLine(x - g(45), base - g(14 + i * 10), x + g(45), base - g(14 + i * 10), P((200, 200, 200), g(4)))
        c.drawRect(skia.Rect.MakeXYWH(x - g(40), base - g(86), g(80), g(42)), P((248, 244, 232), fill=True))
    elif name == "lamp":  # desk lamp
        c.drawLine(x, base, x - g(10), base - g(70), P(INK, g(8)))
        poly(c, [(x - g(42), base - g(70)), (x + g(20), base - g(70)), (x + g(4), base - g(110)), (x - g(28), base - g(110))], P((60, 110, 80), fill=True))
        glow(c, x - g(10), base - g(50), g(170), (255, 220, 150), 120)
    elif name in ("bookshelf", "cabinet", "filing_cabinet", "counter"):
        cc = col or {"bookshelf": (110, 70, 45), "cabinet": (130, 90, 60), "filing_cabinet": (120, 130, 125), "counter": (120, 80, 55)}[name]
        ww, hh = {"bookshelf": (260, 470), "cabinet": (220, 300), "filing_cabinet": (150, 300), "counter": (520, 210)}[name]
        fr = box3d(c, lt, x, base, g(ww), g(hh), g(110), cc, vp)
        if name == "bookshelf":
            for sh in range(4):
                y = fr.top() + g(20) + sh * g(112)
                c.drawLine(fr.left() + g(10), y + g(100), fr.right() - g(10), y + g(100), P(lt.dark(cc, 0.4), g(8)))
                bx = fr.left() + g(16)
                while bx < fr.right() - g(26):
                    bw = g(rnd.randint(14, 26))
                    c.drawRect(skia.Rect.MakeXYWH(bx, y + g(rnd.randint(20, 40)), bw, y + g(96) - (y + g(rnd.randint(20, 40)))),
                               P(rnd.choice([(170, 60, 60), (60, 100, 150), (200, 160, 70), (80, 130, 90), (140, 90, 140)]), fill=True))
                    bx += bw + g(3)
        elif name == "filing_cabinet":
            for k in range(3):
                y = fr.top() + g(14) + k * g(95)
                c.drawRect(skia.Rect.MakeXYWH(fr.left() + g(12), y, fr.width() - g(24), g(80)), P(INK, g(3), alpha=120))
                c.drawLine(fr.centerX() - g(20), y + g(30), fr.centerX() + g(20), y + g(30), P((230, 230, 230), g(6)))
        elif name == "counter":
            for i in range(7):
                bx = fr.left() + g(40) + i * g(65)
                c.drawRect(skia.Rect.MakeXYWH(bx, fr.top() - g(70), g(22), g(70)), P(rnd.choice([(90, 140, 70), (140, 60, 40), (220, 190, 120)]), fill=True))
        cast_shadow(c, lt, x, base, g(ww * 1.1), g(40))
    elif name == "chair":
        cc = col or (120, 75, 50)
        box3d(c, lt, x, base - g(90), g(110), g(16), g(90), cc, vp)
        c.drawRect(skia.Rect.MakeXYWH(x - g(55), base - g(210), g(14), g(120)), P(lt.dark(cc, 0.2), fill=True))
        for dx in (-48, 48):
            c.drawLine(x + g(dx), base - g(90), x + g(dx), base, P(lt.dark(cc, 0.3), g(10)))
        cast_shadow(c, lt, x, base, g(140), g(26))
    elif name == "window":
        ww, hh = g(260), g(330)
        top = base - g(780)
        glow(c, x, top + hh / 2, g(360), lt.key, 110)
        c.drawRect(skia.Rect.MakeXYWH(x - ww / 2, top, ww, hh), skia.Paint(Shader=skia.GradientShader.MakeLinear(
            [(0, top), (0, top + hh)], [rgb(lt.sky0), rgb(lt.sky1)])))
        c.drawRect(skia.Rect.MakeXYWH(x - ww / 2, top, ww, hh), P((240, 230, 210), g(14)))
        c.drawLine(x, top, x, top + hh, P((240, 230, 210), g(10)))
        c.drawLine(x - ww / 2, top + hh / 2, x + ww / 2, top + hh / 2, P((240, 230, 210), g(10)))
        # light shaft onto the floor
        poly(c, [(x - ww / 2, top + hh), (x + ww / 2, top + hh), (x + ww * 0.9 + lt.shadow_dx() * g(200), base + g(260)),
                 (x - ww * 0.2 + lt.shadow_dx() * g(200), base + g(260))], P(lt.key, fill=True, alpha=34))
    elif name == "curtains":
        for d in (-1, 1):
            xx = x + d * g(190)
            cc = col or (150, 50, 60)
            path = skia.Path()
            path.moveTo(xx - g(60), base - g(860))
            path.lineTo(xx + g(60), base - g(860))
            path.quadTo(xx + g(40) + d * g(20) * math.sin(t), base - g(300), xx + g(70), base)
            path.lineTo(xx - g(70), base)
            path.close()
            c.drawPath(path, skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
                [(xx - g(60), 0), (xx + g(60), 0)], [rgb(lt.lit(cc, 0.2)), rgb(lt.dark(cc, 0.4)), rgb(lt.lit(cc, 0.1))], [0, 0.5, 1])))
    elif name == "map_board":
        fr = skia.Rect.MakeXYWH(x - g(170), base - g(720), g(340), g(240))
        c.drawRect(fr, P((180, 140, 95), fill=True))
        c.drawRect(fr, P((90, 60, 40), g(12)))
        for i in range(5):
            px, py = fr.left() + g(30 + (i % 3) * 100), fr.top() + g(25 + (i // 3) * 110)
            c.drawRect(skia.Rect.MakeXYWH(px, py, g(80), g(90)), P((245, 240, 225), fill=True))
            c.drawCircle(px + g(40), py + g(6), g(6), P((200, 40, 40), fill=True))
    elif name == "flag":
        c.drawLine(x, base, x, base - g(560), P((150, 120, 60), g(10)))
        path = skia.Path()
        path.moveTo(x, base - g(550))
        for k in range(9):
            path.lineTo(x + k * g(24), base - g(550) + g(10) * math.sin(t * 3 + k * 0.7))
        for k in range(8, -1, -1):
            path.lineTo(x + k * g(24), base - g(410) + g(10) * math.sin(t * 3 + k * 0.7))
        path.close()
        c.drawPath(path, P(col or (40, 60, 130), fill=True))
        c.drawPath(path, P(INK, g(3), alpha=150))
    elif name == "clock":
        cy = base - g(820)
        c.drawCircle(x, cy, g(60), P((245, 240, 225), fill=True))
        c.drawCircle(x, cy, g(60), P((90, 60, 40), g(10)))
        c.drawLine(x, cy, x + g(40) * math.sin(t * 1.5), cy - g(40) * math.cos(t * 1.5), P(INK, g(5)))
        c.drawLine(x, cy, x + g(26) * math.sin(t * 0.12), cy - g(26) * math.cos(t * 0.12), P(INK, g(7)))
    elif name == "plant":
        box3d(c, lt, x, base, g(90), g(80), g(60), (170, 90, 60), vp)
        for i in range(7):
            a = math.radians(-70 + i * 23 + 4 * math.sin(t * 1.5 + i))
            c.drawLine(x, base - g(80), x + g(130) * math.sin(a), base - g(80) - g(150) * math.cos(a), P((70, 130, 80), g(14)))
        cast_shadow(c, lt, x, base, g(110))
    elif name == "crate":
        box3d(c, lt, x, base, g(150), g(130), g(120), col or (170, 125, 70), vp)
        c.drawLine(x - g(75), base - g(130), x + g(75), base, P(lt.dark((170, 125, 70), 0.4), g(6)))
        cast_shadow(c, lt, x, base, g(170))
    elif name == "paper_stacks":
        for i in range(3):
            box3d(c, lt, x + g(i * 70 - 70), base, g(80), g(60 + 30 * (i % 2)), g(60), (240, 236, 222), vp)
    elif name == "chandelier":
        cy = base - g(1000)
        c.drawLine(x, cy - g(200), x, cy, P((180, 140, 60), g(5)))
        c.drawOval(skia.Rect.MakeXYWH(x - g(110), cy - g(20), g(220), g(50)), P((210, 170, 80), fill=True))
        for i in range(5):
            gx = x - g(90) + i * g(45)
            glow(c, gx, cy - g(20), g(70), (255, 220, 150), 170)
            c.drawCircle(gx, cy - g(20), g(9), P((255, 245, 200), fill=True))
    elif name == "radio":
        box3d(c, lt, x, base, g(140), g(110), g(60), (130, 80, 45), vp)
        c.drawCircle(x - g(30), base - g(55), g(30), P((70, 50, 35), fill=True))
        c.drawCircle(x + g(40), base - g(70), g(10), P((230, 210, 160), fill=True))
    elif name == "telephone":
        c.drawOval(skia.Rect.MakeXYWH(x - g(40), base - g(40), g(80), g(40)), P((30, 30, 34), fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(x - g(50), base - g(62), g(100), g(22)), g(10), g(10), P((30, 30, 34), fill=True))
    # ---- exterior items
    elif name == "farmhouse":
        cc = col or (226, 214, 190)
        fr = box3d(c, lt, x, base, g(520), g(300), g(260), cc, vp)
        roof = [(fr.left() - g(30), fr.top()), (fr.right() + g(30), fr.top()), (fr.right() - g(40), fr.top() - g(140)), (fr.left() + g(40), fr.top() - g(140))]
        poly(c, roof, P(lt.dark((150, 70, 50), 0.1), fill=True))
        poly(c, roof, P(INK, 3, alpha=150))
        for i in range(12):
            yy = fr.top() - g(12 * i)
            c.drawLine(fr.left() - g(20) + g(5 * i), yy, fr.right() + g(20) - g(5 * i), yy, P((120, 55, 40), g(2), alpha=120))
        box3d(c, lt, fr.left() + g(90), fr.top() - g(80), g(40), g(110), g(40), (150, 90, 70), vp)  # chimney
        for wx in (-150, 150):
            c.drawRect(skia.Rect.MakeXYWH(x + g(wx) - g(45), base - g(220), g(90), g(90)), P((255, 220, 150), fill=True))
            c.drawRect(skia.Rect.MakeXYWH(x + g(wx) - g(45), base - g(220), g(90), g(90)), P((120, 90, 70), g(6)))
        c.drawRect(skia.Rect.MakeXYWH(x - g(45), base - g(170), g(90), g(170)), P((110, 70, 50), fill=True))
        poly(c, [(fr.left() - g(10), base - g(190)), (fr.right() + g(10), base - g(190)), (fr.right() + g(40), base - g(160)), (fr.left() - g(40), base - g(160))],
             P((170, 160, 140), fill=True))  # veranda roof
        cast_shadow(c, lt, x, base, g(600), g(60))
    elif name == "windmill":
        tx = x
        for d in (-1, 1):
            c.drawLine(tx + d * g(70), base, tx + d * g(10), base - g(560), P((90, 80, 80), g(8)))
        for k in range(6):
            yy = base - g(90 * k)
            c.drawLine(tx - g(70) + g(10 * k), yy, tx + g(70) - g(10 * k), yy - g(90), P((90, 80, 80), g(4)))
        hub = (tx, base - g(580))
        for i in range(12):
            a = t * 2.2 + i * math.pi / 6
            c.drawLine(*hub, hub[0] + g(150) * math.cos(a), hub[1] + g(150) * math.sin(a), P(lt.lit((220, 220, 225), 0.2), g(14), cap=False))
        c.drawCircle(*hub, g(20), P((70, 60, 60), fill=True))
        poly(c, [(hub[0], hub[1] - g(10)), (hub[0] + g(150), hub[1] - g(40)), (hub[0] + g(150), hub[1] + g(20))], P((200, 60, 50), fill=True))
        cast_shadow(c, lt, tx, base, g(180), g(20), 2.0)
    elif name == "water_tank":
        cc = col or (180, 185, 190)
        r = skia.Rect.MakeXYWH(x - g(110), base - g(380), g(220), g(200))
        c.drawRect(r, skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear([(r.left(), 0), (r.right(), 0)],
                   [rgb(lt.lit(cc, 0.3 if lt.side < 0 else 0)), rgb(lt.dark(cc, 0.4 if lt.side < 0 else 0.1))])))
        for k in range(6):
            c.drawLine(r.left(), r.top() + g(30 * k + 15), r.right(), r.top() + g(30 * k + 15), P(lt.dark(cc, 0.3), g(4)))
        c.drawOval(skia.Rect.MakeXYWH(r.left(), r.top() - g(30), r.width(), g(60)), P(lt.lit(cc, 0.4), fill=True))
        for dx in (-90, 90):
            c.drawLine(x + g(dx), r.bottom(), x + g(dx), base, P((90, 70, 60), g(14)))
        cast_shadow(c, lt, x, base, g(260), g(30), 1.5)
    elif name in ("gum_tree", "tree"):
        trunk = (225, 215, 200) if name == "gum_tree" else (100, 70, 50)
        path = skia.Path()
        path.moveTo(x - g(26), base)
        path.quadTo(x - g(10), base - g(250), x - g(40), base - g(470))
        path.lineTo(x + g(10), base - g(470))
        path.quadTo(x + g(20), base - g(250), x + g(30), base)
        path.close()
        c.drawPath(path, P(lt.lit(trunk, 0.1), fill=True))
        c.drawLine(x - g(30), base - g(350), x - g(140), base - g(480), P(trunk, g(18)))
        c.drawLine(x + g(5), base - g(300), x + g(130), base - g(440), P(trunk, g(16)))
        leaf = (95, 125, 85) if name == "gum_tree" else (70, 120, 70)
        for i in range(9):
            cx = x + g(rnd.uniform(-200, 200))
            cy = base - g(rnd.uniform(440, 640))
            rr = g(rnd.uniform(70, 120))
            sway = g(6) * math.sin(t * 1.2 + i)
            c.drawCircle(cx + sway, cy, rr, P(lt.dark(leaf, 0.35), fill=True))
            c.drawCircle(cx + sway - lt.shadow_dx() * rr * 0.25, cy - rr * 0.25, rr * 0.75, P(lt.lit(leaf, 0.3), fill=True))
        cast_shadow(c, lt, x, base, g(320), g(40), 1.4)
    elif name == "fence":  # a fence running back toward the vanishing point
        n = 9
        pts = []
        for k in range(n):
            u = k / (n - 1)
            px, py = lerp(x, vp[0] + (x - vp[0]) * 0.18, u), lerp(base, vp[1] + (base - vp[1]) * 0.18, u)
            hh = lerp(g(190), g(190) * 0.18, u)
            pts.append((px, py, hh))
            c.drawLine(px, py, px, py - hh, P((120, 90, 60), max(2, lerp(g(14), g(3), u))))
        for fr in (0.85, 0.5):
            for a, b in zip(pts, pts[1:]):
                c.drawLine(a[0], a[1] - a[2] * fr, b[0], b[1] - b[2] * fr, P((80, 70, 60), max(1.5, g(4) * (1 - 0.5 * (a[1] < base)))))
    elif name == "broken_fence":
        for k in range(5):
            xx = x - g(240) + k * g(120)
            ang = [0, 25, -60, 10, 80][k]
            c.save()
            c.translate(xx, base)
            c.rotate(ang)
            c.drawLine(0, 0, 0, -g(190), P((120, 90, 60), g(16)))
            c.restore()
        c.drawLine(x - g(240), base - g(150), x - g(130), base - g(90), P((80, 70, 60), g(5)))
        c.drawLine(x + g(60), base - g(60), x + g(240), base - g(170), P((80, 70, 60), g(5)))
    elif name == "tent":
        cc = col or (170, 160, 110)
        fr = [(x - g(190), base), (x, base - g(260)), (x + g(190), base)]
        poly(c, fr, P(lt.lit(cc, 0.15), fill=True))
        poly(c, [(x, base - g(260)), (x + g(190), base), (x + g(260), base - g(40)), (x + g(80), base - g(280))], P(lt.dark(cc, 0.35), fill=True))
        poly(c, [(x - g(40), base), (x, base - g(130)), (x + g(40), base)], P(lt.dark(cc, 0.6), fill=True))
        poly(c, fr, P(INK, 3, alpha=150))
        cast_shadow(c, lt, x, base, g(420), g(40))
    elif name == "haystack":
        cc = (225, 185, 90)
        c.drawOval(skia.Rect.MakeXYWH(x - g(150), base - g(200), g(300), g(230)), P(lt.lit(cc, 0.15), fill=True))
        c.drawOval(skia.Rect.MakeXYWH(x - g(150) - lt.shadow_dx() * g(-60), base - g(200), g(300), g(230)), P(lt.dark(cc, 0.3), fill=True, alpha=90))
        cast_shadow(c, lt, x, base, g(320))
    elif name == "dam":  # a farm dam / watering hole
        c.drawOval(skia.Rect.MakeXYWH(x - g(420), base - g(70), g(840), g(150)), P((120, 95, 70), fill=True))
        c.drawOval(skia.Rect.MakeXYWH(x - g(380), base - g(55), g(760), g(115)), skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
            [(0, base - g(55)), (0, base + g(60))], [rgb(lt.lit((120, 150, 190), 0.3)), rgb((60, 80, 120))])))
        for i in range(4):
            yy = base - g(20) + i * g(22)
            off = g(30) * math.sin(t * 1.5 + i)
            c.drawLine(x - g(200) + off, yy, x + g(200) + off, yy, P((255, 255, 255), g(3), alpha=90))
    elif name == "army_truck":
        draw_truck(c, lt, x, base, s, vp, t, 0)
    elif name == "telegraph_pole":
        c.drawLine(x, base, x, base - g(620), P((110, 85, 65), g(14)))
        c.drawLine(x - g(70), base - g(580), x + g(70), base - g(580), P((110, 85, 65), g(10)))
    elif name == "rock":
        poly(c, [(x - g(120), base), (x - g(80), base - g(90)), (x + g(30), base - g(120)), (x + g(120), base)], P(lt.lit((150, 120, 100), 0.1), fill=True))
        cast_shadow(c, lt, x, base, g(260))
    elif name == "lamp_post":
        c.drawLine(x, base, x, base - g(560), P((40, 45, 50), g(14)))
        glow(c, x, base - g(560), g(180), (255, 215, 150), 160)
        c.drawRect(skia.Rect.MakeXYWH(x - g(26), base - g(600), g(52), g(60)), P((255, 230, 170), fill=True))
    elif name == "awning_shop":
        fr = box3d(c, lt, x, base, g(380), g(420), g(80), col or (200, 170, 140), vp)
        for i in range(8):
            c.drawRect(skia.Rect.MakeXYWH(fr.left() + i * fr.width() / 8, fr.top() + g(60), fr.width() / 8, g(70)),
                       P((200, 60, 60) if i % 2 else (245, 235, 220), fill=True))
        c.drawRect(skia.Rect.MakeXYWH(fr.left() + g(40), fr.top() + g(170), fr.width() - g(80), g(170)), P((255, 215, 140), fill=True))


def draw_truck(c, lt, x, base, s, vp, t, moving):
    g = lambda v: v * s
    cc = (110, 115, 80)
    bob = g(3) * math.sin(t * 20) if moving else 0
    box3d(c, lt, x - g(90), base - g(70) + bob, g(330), g(150), g(170), lt.dark(cc, 0.05), vp)     # tray
    box3d(c, lt, x + g(170), base - g(70) + bob, g(170), g(200), g(150), cc, vp)                    # cab
    c.drawRect(skia.Rect.MakeXYWH(x + g(150), base - g(250) + bob, g(80), g(70)), P((170, 200, 220), fill=True))
    for wx in (-180, 0, 200):
        rot = t * 12 if moving else 0
        c.drawCircle(x + g(wx), base - g(40), g(48), P(INK, fill=True))
        c.drawCircle(x + g(wx), base - g(40), g(20), P((120, 120, 120), fill=True))
        c.drawLine(x + g(wx), base - g(40), x + g(wx) + g(18) * math.cos(rot), base - g(40) + g(18) * math.sin(rot), P(INK, g(4)))
    cast_shadow(c, lt, x, base, g(560), g(46))
    if moving:
        for i in range(5):
            k = (t * 2 + i / 5) % 1
            c.drawCircle(x - g(320) - g(160) * k, base - g(30) - g(60) * k, g(30 + 50 * k), P((210, 180, 140), fill=True, alpha=int(150 * (1 - k))))


# --------------------------------------------------------------- sets
def draw_set(c, place, lt, t, cam_x):
    kind = place.get("kind", "exterior")
    vp = (540 + cam_x * 0.0, HORIZON if kind == "exterior" else 700)
    if kind == "interior":
        _interior(c, place, lt, t, vp)
    else:
        _exterior(c, place, lt, t, vp)
    return vp


def _interior(c, pl, lt, t, vp):
    wall = hexc(pl.get("wall", "#8a6f5c"))
    floor = hexc(pl.get("floor_color", "#7a5236"))
    # back wall with key-light falloff
    c.drawRect(skia.Rect.MakeLTRB(-600, 0, W + 600, WALL_BASE), skia.Paint(Shader=skia.GradientShader.MakeLinear(
        [(-600 if lt.side < 0 else W + 600, 0), (W + 600 if lt.side < 0 else -600, 0)],
        [rgb(lt.lit(wall, 0.25)), rgb(lt.dark(wall, 0.35))])))
    for i in range(-6, 14):  # wall panels
        x = i * 180
        c.drawRect(skia.Rect.MakeXYWH(x + 20, 640, 140, 470), P(lt.dark(wall, 0.25), 5, alpha=110))
    c.drawRect(skia.Rect.MakeLTRB(-600, 600, W + 600, 616), P(lt.lit(wall, 0.4), fill=True))
    c.drawRect(skia.Rect.MakeLTRB(-600, 0, W + 600, 140), P(lt.dark(wall, 0.5), fill=True))
    c.drawRect(skia.Rect.MakeLTRB(-600, WALL_BASE - 40, W + 600, WALL_BASE), P(lt.dark(wall, 0.45), fill=True))
    # floor with perspective boards/tiles
    c.drawRect(skia.Rect.MakeLTRB(-600, WALL_BASE, W + 600, H + 200), skia.Paint(Shader=skia.GradientShader.MakeLinear(
        [(0, WALL_BASE), (0, H)], [rgb(lt.dark(floor, 0.3)), rgb(lt.lit(floor, 0.15))])))
    style = pl.get("floor", "planks")
    for i in range(-30, 31):
        x0 = vp[0] + i * 55
        x1 = vp[0] + (x0 - vp[0]) * (H + 200 - vp[1]) / (WALL_BASE - vp[1])
        c.drawLine(x0, WALL_BASE, x1, H + 200, P(lt.dark(floor, 0.45), 3, alpha=150))
    if style == "tiles":
        y = WALL_BASE
        step = 30
        while y < H + 200:
            c.drawLine(-600, y, W + 600, y, P(lt.dark(floor, 0.45), 3, alpha=150))
            step *= 1.28
            y += step
    if pl.get("carpet"):
        cc = hexc(pl["carpet"])
        poly(c, [(vp[0] - 260, WALL_BASE + 120), (vp[0] + 260, WALL_BASE + 120), (vp[0] + 700, H + 100), (vp[0] - 700, H + 100)], P(lt.dark(cc, 0.1), fill=True))
        poly(c, [(vp[0] - 220, WALL_BASE + 150), (vp[0] + 220, WALL_BASE + 150), (vp[0] + 600, H + 60), (vp[0] - 600, H + 60)], P(lt.lit(cc, 0.3), 8))
    for it in pl.get("items", []):
        nm, x, depth = (it, None, 0.0) if isinstance(it, str) else (it.get("name"), it.get("x"), it.get("z", 0.0))
        if x is None:
            continue
        s = lerp(0.95, 0.55, depth)
        base = lerp(WALL_BASE + 60, WALL_BASE + 8, depth) if depth > 0 else WALL_BASE + 40
        item(c, lt, nm, x * W, base, s, vp, t, hexc(it.get("color")) if isinstance(it, dict) and it.get("color") else None)
    # ceiling lamps glow
    for lx in pl.get("ceiling_lamps", []):
        glow(c, lx * W, 210, 260, lt.key, 140)
        c.drawLine(lx * W, 0, lx * W, 170, P(INK, 4))
        c.drawCircle(lx * W, 200, 26, P((255, 240, 200), fill=True))


def _exterior(c, pl, lt, t, vp):
    # sky
    vgrad(c, -600, -200, W + 1200, HORIZON + 260, lt.sky0, lt.sky1)
    sx = W * (0.18 if lt.side < 0 else 0.82)
    if lt.name in ("golden", "sunset", "day", "dust"):
        glow(c, sx, HORIZON - 380, 520, lt.key, 200)
        c.drawCircle(sx, HORIZON - 380, 80, P(mix(lt.key, (255, 255, 255), 0.5), fill=True))
    if lt.name == "night":
        rnd = random.Random(3)
        for i in range(80):
            c.drawCircle(rnd.uniform(-300, W + 300), rnd.uniform(0, HORIZON - 200), rnd.uniform(1.5, 3.5),
                         P((255, 255, 255), fill=True, alpha=int(150 + 100 * math.sin(t * 2 + i))))
        c.drawCircle(sx, 300, 70, P((250, 245, 230), fill=True))
    rnd = random.Random(7)
    for i in range(5):  # soft clouds lit from the key side
        cx = (rnd.uniform(-300, W + 300) + t * 10 * rnd.uniform(0.5, 1.5)) % (W + 700) - 350
        cy = rnd.uniform(150, HORIZON - 450)
        w = rnd.uniform(220, 380)
        cp = blurred(P(mix(lt.sky1, (255, 255, 255), 0.5), fill=True, alpha=170), 12)
        c.drawOval(skia.Rect.MakeXYWH(cx, cy, w, w * 0.28), cp)
        c.drawOval(skia.Rect.MakeXYWH(cx + w * 0.25, cy - w * 0.1, w * 0.5, w * 0.3), cp)
    # far hills: pale, soft
    c.saveLayer(None, skia.Paint(ImageFilter=skia.ImageFilters.Blur(5, 5)))
    far = mix(lt.sky1, hexc(pl.get("hills", "#8a7f9a")), 0.45)
    for i, (cx, ww, hh) in enumerate(((-100, 900, 170), (500, 1000, 230), (1150, 900, 180))):
        c.drawOval(skia.Rect.MakeXYWH(cx - ww / 2, HORIZON - hh, ww, hh * 2), P(mix(far, lt.sky1, 0.25 * i), fill=True))
    c.restore()
    # ground
    ground = hexc(pl.get("ground", "#c9a45c"))
    vgrad(c, -600, HORIZON, W + 1200, H - HORIZON + 300, mix(ground, lt.sky1, 0.35), lt.lit(ground, 0.12))
    lines = pl.get("ground_style", "furrows")
    if lines in ("furrows", "wheat"):
        for i in range(-40, 41):
            x1 = vp[0] + i * 120
            c.drawLine(vp[0] + i * 6, HORIZON + 6, x1, H + 300, P(lt.dark(ground, 0.25), 3, alpha=120))
    if lines == "wheat":
        rnd = random.Random(9)
        for i in range(260):
            y = HORIZON + (H - HORIZON) * (rnd.random() ** 1.7)
            k = (y - HORIZON) / (H - HORIZON)
            x = vp[0] + (rnd.uniform(-1, 1)) * (80 + 1400 * k)
            h = 10 + 60 * k
            sway = 6 * k * math.sin(t * 2 + i)
            c.drawLine(x, y, x + sway, y - h, P(lt.lit((235, 190, 90), 0.2), max(1.5, 4 * k)))
    if lines == "road":
        poly(c, [(vp[0] - 30, HORIZON + 4), (vp[0] + 30, HORIZON + 4), (vp[0] + 700, H + 300), (vp[0] - 700, H + 300)],
             P(mix(ground, (150, 120, 100), 0.5), fill=True))
    if lines == "cobbles":
        y, step = HORIZON + 10, 12
        while y < H + 200:
            c.drawLine(-600, y, W + 600, y, P(lt.dark(ground, 0.3), 2, alpha=120))
            step *= 1.18
            y += step
        for i in range(-30, 31):
            c.drawLine(vp[0] + i * 8, HORIZON, vp[0] + i * 140, H + 300, P(lt.dark(ground, 0.3), 2, alpha=110))
    # haze at the horizon
    c.drawRect(skia.Rect.MakeXYWH(-600, HORIZON - 120, W + 1200, 240), skia.Paint(Shader=skia.GradientShader.MakeLinear(
        [(0, HORIZON - 120), (0, HORIZON + 120)],
        [rgb(lt.sky1, 0), rgb(mix(lt.sky1, (255, 255, 255), 0.25), 150), rgb(lt.sky1, 0)], [0, 0.5, 1])))
    items = sorted(pl.get("items", []), key=lambda it: -(it.get("z", 0.5) if isinstance(it, dict) else 0.5))
    for it in items:
        if isinstance(it, str):
            continue
        z = float(it.get("z", 0.5))
        s = lerp(1.0, 0.25, z)
        base = lerp(FLOOR - 40, HORIZON + 14, z)
        x = vp[0] + (it.get("x", 0.5) * W - vp[0]) * lerp(1.0, 0.6, z)
        if z > 0.55:  # far things are softer
            c.saveLayer(None, skia.Paint(ImageFilter=skia.ImageFilters.Blur(2.5 * z, 2.5 * z)))
            item(c, lt, it.get("name"), x, base, s, vp, t, hexc(it["color"]) if it.get("color") else None)
            c.restore()
        else:
            item(c, lt, it.get("name"), x, base, s, vp, t, hexc(it["color"]) if it.get("color") else None)


# --------------------------------------------------------------- flat stickmen
def fk(a, p, ht):
    """Forward kinematics for a character `ht` px tall (head = ht/6, legs 45%, arms 35%)."""
    f = a.facing
    r = ht / 11
    leg = ht * 0.45
    arm = ht * 0.35
    torso = ht - leg - 2 * r - ht * 0.02
    th = sh = leg / 2
    ua = fa = arm / 2
    seg = lambda x, y, ang, ln: (x + f * ln * math.sin(math.radians(ang)), y + ln * math.cos(math.radians(ang)))
    lk = seg(0, 0, p["ll1"], th)
    lf = seg(*lk, p["ll1"] + p["ll2"], sh)
    rk = seg(0, 0, p["rl1"], th)
    rf = seg(*rk, p["rl1"] + p["rl2"], sh)
    low = max(lf[1], rf[1])
    dy = p["dy"] * ht / 620
    hip = (a.x, a.ground - low - 2 + (dy if dy < 0 else dy * 0.35))
    tor = math.radians(p["torso"])
    neck = (hip[0] + f * torso * math.sin(tor), hip[1] - torso * math.cos(tor))
    hang = tor + math.radians(p["head"])
    head = (neck[0] + f * (r + ht * 0.02) * math.sin(hang), neck[1] - (r + ht * 0.02) * math.cos(hang))
    shl = (lerp(neck[0], hip[0], 0.06), lerp(neck[1], hip[1], 0.06))
    le = seg(*shl, p["la1"] + p["torso"], ua)
    lh = seg(*le, p["la1"] + p["torso"] + p["la2"], fa)
    re = seg(*shl, p["ra1"] + p["torso"], ua)
    rh = seg(*re, p["ra1"] + p["torso"] + p["ra2"], fa)
    off = lambda q: (hip[0] + q[0], hip[1] + q[1])
    return dict(hip=hip, neck=neck, head=head, sh=shl, le=le, lh=lh, re=re, rh=rh,
                lk=off(lk), lf=off(lf), rk=off(rk), rf=off(rf), r=r, tor=tor)


class Char:
    def __init__(self, cid, spec):
        self.id = cid
        self.x = 540.0
        self.facing = 1
        self.ground = FLOOR
        self.ht = 900.0
        self.last_pose = dict(BASE)
        self.face = "neutral"
        self.prop = ""
        self.update(spec)

    def update(self, s):
        lk = s.get("look", {})
        for k in ("hat", "outfit", "hair", "moustache", "glasses", "brows", "bowtie", "belt"):
            if k in lk:
                setattr(self, k, lk[k])
        self.cloth = hexc(lk.get("color", "#6b4bd8")) if lk.get("color") or not hasattr(self, "cloth") else self.cloth
        self.hat_color = hexc(lk.get("hat_color", "#222228")) if lk.get("hat_color") or not hasattr(self, "hat_color") else self.hat_color
        self.hair_color = hexc(lk.get("hair_color", "#3c2818")) if lk.get("hair_color") or not hasattr(self, "hair_color") else self.hair_color
        if "height" in lk:
            self.ht_base = 900 * float(lk["height"])
        for k, v in (("hat", ""), ("outfit", "jacket"), ("hair", ""), ("moustache", False), ("glasses", ""), ("brows", "thin"),
                     ("bowtie", ""), ("belt", False), ("ht_base", 900.0)):
            if not hasattr(self, k):
                setattr(self, k, v)


def draw_char(c, ch, p, t, lt, talking=False, look=0):
    j = fk(ch, p, ch.ht)
    k = ch.ht / 900
    lw = 12 * k * 1.25
    r = j["r"]
    f = ch.facing
    limb = P(INK, lw)
    # cast shadow on the floor
    cast_shadow(c, lt, j["hip"][0], ch.ground, ch.ht * 0.3, 28 * k, 1.6, 120)
    # back limbs
    c.drawLine(*j["hip"], *j["lk"], limb)
    c.drawLine(*j["lk"], *j["lf"], limb)
    c.drawLine(*j["sh"], *j["le"], limb)
    c.drawLine(*j["le"], *j["lh"], limb)
    _shoe(c, j["lf"], f, k)
    _hand(c, j["lh"], k, lt)
    if ch.hair == "long":
        c.drawRoundRect(skia.Rect.MakeXYWH(j["head"][0] - r * 1.05, j["head"][1] - r * 0.9, r * 2.1, r * 2.2), r * 0.8, r * 0.8, P(ch.hair_color, fill=True))
    c.drawLine(*j["hip"], *j["neck"], limb)
    c.drawLine(*j["hip"], *j["rk"], limb)
    c.drawLine(*j["rk"], *j["rf"], limb)
    _shoe(c, j["rf"], f, k)
    _clothes(c, ch, j, k, lt)
    _head(c, ch, j, k, t, lt, talking, look)
    # front arm in front of everything
    c.drawLine(*j["sh"], *j["re"], limb)
    c.drawLine(*j["re"], *j["rh"], limb)
    _hand(c, j["rh"], k, lt)
    if ch.prop:
        hand_prop(c, ch.prop, j["rh"], k, t, f, lt)
    return j


def _shoe(c, q, f, k):
    c.drawOval(skia.Rect.MakeXYWH(q[0] - 22 * k + f * 14 * k, q[1] - 12 * k, 48 * k, 22 * k), P(INK, fill=True))


def _hand(c, q, k, lt):
    c.drawCircle(*q, 13 * k, P((255, 255, 255), fill=True))
    c.drawCircle(*q, 13 * k, P(INK, 4 * k))


def _clothes(c, ch, j, k, lt):
    """One flat clothing shape over the body line; thin darker edge on the shadow side."""
    top, hip = j["neck"], j["hip"]
    dx, dy = hip[0] - top[0], hip[1] - top[1]
    n = math.hypot(dx, dy) or 1
    ux, uy = dx / n, dy / n
    nx, ny = -uy, ux
    o = ch.outfit
    if o in ("none", ""):
        return
    wt, wb = 66 * k, 54 * k
    a = (top[0] + ux * 10 * k, top[1] + uy * 10 * k)
    ln = {"jacket": 0.78, "waistcoat": 0.7, "shirt": 0.74, "uniform": 0.84, "dress": 1.4, "overalls": 1.12, "coat": 1.35, "apron": 1.2}.get(o, 0.78)
    b = (top[0] + dx * ln, top[1] + dy * ln)
    if o in ("dress", "coat"):
        wb = 95 * k if o == "dress" else 70 * k
    pts = [(a[0] + nx * wt, a[1] + ny * wt), (b[0] + nx * wb, b[1] + ny * wb), (b[0] - nx * wb, b[1] - ny * wb), (a[0] - nx * wt, a[1] - ny * wt)]
    col = ch.cloth
    path = skia.Path()
    path.moveTo(*pts[0])
    for q in pts[1:]:
        path.lineTo(*q)
    path.close()
    fp = P(col, fill=True)
    c.drawPath(path, fp)
    rp = P(col, 18 * k)
    c.drawPath(path, rp)
    # darker edge on the shadow side
    sd = 1 if (nx * lt.shadow_dx()) > 0 else -1
    c.drawLine(pts[0 if sd > 0 else 3][0], pts[0 if sd > 0 else 3][1], pts[1 if sd > 0 else 2][0], pts[1 if sd > 0 else 2][1],
               P(lt.dark(col, 0.5), 10 * k))
    c.drawPath(path, P(INK, 4 * k, alpha=200))
    mid = lambda u, s: (lerp(a[0], b[0], u) + nx * s, lerp(a[1], b[1], u) + ny * s)
    if o == "jacket":  # lapels
        c.drawLine(*mid(0.0, -wt * 0.5), *mid(0.45, 0), P(mix(col, (0, 0, 0), 0.35), 6 * k))
        c.drawLine(*mid(0.0, wt * 0.5), *mid(0.45, 0), P(mix(col, (0, 0, 0), 0.35), 6 * k))
    if o in ("waistcoat",):
        for u in (0.3, 0.5, 0.7):
            c.drawCircle(*mid(u, 0), 5 * k, P((240, 220, 160), fill=True))
    if o == "uniform" or ch.belt:
        c.drawLine(*mid(0.82, -wb * 1.05), *mid(0.82, wb * 1.05), P((90, 60, 35), 12 * k))
        c.drawRect(skia.Rect.MakeXYWH(*mid(0.82, -9 * k), 18 * k, 14 * k), P((220, 190, 90), fill=True))
        for u in (0.25, 0.45, 0.65):
            c.drawCircle(*mid(u, 0), 5 * k, P((220, 190, 90), fill=True))
        c.drawRect(skia.Rect.MakeXYWH(*mid(0.28, wt * 0.35), 22 * k, 16 * k), P(mix(col, (0, 0, 0), 0.25), fill=True))
    if o == "overalls":
        c.drawLine(*mid(0.0, -wt * 0.6), *mid(0.3, -wt * 0.6), P(mix(col, (255, 255, 255), 0.3), 6 * k))
        c.drawLine(*mid(0.0, wt * 0.6), *mid(0.3, wt * 0.6), P(mix(col, (255, 255, 255), 0.3), 6 * k))
        c.drawRect(skia.Rect.MakeXYWH(*mid(0.45, -24 * k), 48 * k, 36 * k), P(INK, 3 * k, alpha=160))
    if o == "apron":
        c.drawLine(*mid(0.3, -wb), *mid(0.3, wb), P((240, 240, 240), 6 * k))
    if ch.bowtie:
        bc = hexc(ch.bowtie)
        bx, by = mid(0.04, 0)
        poly(c, [(bx, by), (bx - 18 * k, by - 11 * k), (bx - 18 * k, by + 11 * k)], P(bc, fill=True))
        poly(c, [(bx, by), (bx + 18 * k, by - 11 * k), (bx + 18 * k, by + 11 * k)], P(bc, fill=True))


def _head(c, ch, j, k, t, lt, talking, look):
    hx, hy = j["head"]
    r = j["r"]
    f = ch.facing
    tilt = math.degrees(j["tor"]) * 0.3 * f
    c.save()
    c.translate(hx, hy)
    c.rotate(tilt)
    # head: flat white with a thin shadow-side edge and a heavy outline
    c.drawCircle(0, 0, r, P((255, 255, 255), fill=True))
    c.drawArc(skia.Rect.MakeXYWH(-r + 5 * k, -r + 5 * k, 2 * r - 10 * k, 2 * r - 10 * k), -60 if lt.shadow_dx() > 0 else 120, 120, False,
              P(mix((255, 255, 255), lt.shadow, 0.25), 8 * k))
    c.drawCircle(0, 0, r, P(INK, 7 * k))
    if ch.hair and ch.hair != "long" and ch.hat not in ("top", "bowler", "slouch", "helmet", "cap", "straw", "kepi"):
        c.save()
        clip = skia.Path()
        clip.addCircle(0, 0, r)
        c.clipPath(clip, doAntiAlias=True)
        c.drawRect(skia.Rect.MakeXYWH(-r, -r, 2 * r, r * 0.75), P(ch.hair_color, fill=True))
        c.restore()
        c.drawArc(skia.Rect.MakeXYWH(-r, -r, 2 * r, 2 * r), 190, 160, False, P(INK, 7 * k))
        if ch.hair == "bun":
            c.drawCircle(0, -r * 1.05, r * 0.35, P(ch.hair_color, fill=True))
    if ch.hair == "long":
        c.save()
        clip = skia.Path()
        clip.addCircle(0, 0, r)
        c.clipPath(clip, doAntiAlias=True)
        c.drawRect(skia.Rect.MakeXYWH(-r, -r, 2 * r, r * 0.7), P(ch.hair_color, fill=True))
        c.restore()
    cx = f * r * 0.12
    face = ch.face
    blink = (t + hash(ch.id) % 7 * 0.41) % 3.2 < 0.1
    # brows
    bw = (9 if ch.brows == "bushy" else 5) * k
    bi, bo = {"angry": (0.14, -0.06), "sad": (-0.1, 0.06), "shock": (-0.2, -0.16), "smug": (0.05, -0.1), "worried": (-0.12, 0.04)}.get(face, (0, 0))
    for s in (-1, 1):
        c.drawLine(cx + s * r * 0.14, -r * 0.36 + bi * r, cx + s * r * 0.5, -r * 0.36 + bo * r, P(INK, bw))
    # eyes: small black ovals
    for s in (-1, 1):
        ex = cx + s * r * 0.3 + look * r * 0.05
        if blink:
            c.drawLine(ex - r * 0.08, -r * 0.08, ex + r * 0.08, -r * 0.08, P(INK, 4 * k))
        elif face == "shock":
            c.drawCircle(ex, -r * 0.08, r * 0.13, P((255, 255, 255), fill=True))
            c.drawCircle(ex, -r * 0.08, r * 0.13, P(INK, 4 * k))
            c.drawCircle(ex, -r * 0.08, r * 0.05, P(INK, fill=True))
        else:
            c.drawOval(skia.Rect.MakeXYWH(ex - r * 0.065, -r * 0.18, r * 0.13, r * 0.2), P(INK, fill=True))
    if ch.glasses:
        for s in (-1, 1):
            c.drawCircle(cx + s * r * 0.3, -r * 0.08, r * 0.2, P(INK, 4.5 * k))
        c.drawLine(cx - r * 0.1, -r * 0.1, cx + r * 0.1, -r * 0.1, P(INK, 4 * k))
    # mouth
    my = r * 0.38
    op = max(0.0, math.sin(t * 16) * 0.6 + math.sin(t * 6.7) * 0.4) if talking else 0
    if face in ("shock", "worried") or op > 0.2:
        h = r * (0.12 + 0.2 * max(op, 0.5 if face in ("shock", "worried") else 0))
        c.drawOval(skia.Rect.MakeXYWH(cx - r * 0.13, my - h / 2, r * 0.26, h), P(INK, fill=True))
        c.drawOval(skia.Rect.MakeXYWH(cx - r * 0.07, my, r * 0.14, h * 0.4), P((220, 90, 100), fill=True))
    else:
        path = skia.Path()
        if face in ("happy", "excited"):
            path.moveTo(cx - r * 0.22, my - r * 0.04)
            path.quadTo(cx, my + r * 0.2, cx + r * 0.22, my - r * 0.04)
        elif face == "smug":  # sly one-sided smile
            path.moveTo(cx - r * 0.18, my + r * 0.04)
            path.quadTo(cx + r * 0.05, my + r * 0.08, cx + f * r * 0.24, my - r * 0.1)
        elif face in ("sad", "angry"):
            path.moveTo(cx - r * 0.18, my + r * 0.08)
            path.quadTo(cx, my - r * 0.08, cx + r * 0.18, my + r * 0.08)
        else:
            path.moveTo(cx - r * 0.13, my)
            path.lineTo(cx + r * 0.13, my)
        c.drawPath(path, P(INK, 6 * k))
    if ch.moustache:
        for s in (-1, 1):
            path = skia.Path()
            path.moveTo(cx, my - r * 0.14)
            path.quadTo(cx + s * r * 0.2, my - r * 0.24, cx + s * r * 0.34, my - r * 0.1)
            path.quadTo(cx + s * r * 0.42, my - r * 0.02, cx + s * r * 0.36, my - r * 0.18)
            c.drawPath(path, P(INK, 7 * k))
    # hats
    hc = ch.hat_color
    if ch.hat == "top":
        c.drawRect(skia.Rect.MakeXYWH(-r * 0.62, -r * 2.1, r * 1.24, r * 1.25), P(hc, fill=True))
        c.drawRect(skia.Rect.MakeXYWH(-r * 0.62, -r * 1.12, r * 1.24, r * 0.16), P(mix(hc, (255, 255, 255), 0.25), fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(-r * 1.0, -r * 0.94, r * 2.0, r * 0.14), 6, 6, P(hc, fill=True))
    elif ch.hat == "bowler":
        c.drawArc(skia.Rect.MakeXYWH(-r * 0.75, -r * 1.55, r * 1.5, r * 1.3), 180, 180, True, P(hc, fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(-r * 1.0, -r * 0.95, r * 2.0, r * 0.16), 8, 8, P(hc, fill=True))
    elif ch.hat == "slouch":  # Australian army slouch hat, left brim pinned up
        c.drawArc(skia.Rect.MakeXYWH(-r * 0.78, -r * 1.55, r * 1.56, r * 1.25), 180, 180, True, P(hc, fill=True))
        c.drawLine(-r * 0.75, -r * 1.05, r * 0.75, -r * 1.05, P(mix(hc, (0, 0, 0), 0.4), 8 * k))
        poly(c, [(-r * 0.1, -r * 0.95), (r * 1.25, -r * 0.9), (r * 1.15, -r * 0.8), (-r * 0.1, -r * 0.82)], P(hc, fill=True))
        poly(c, [(-r * 0.1, -r * 0.95), (-r * 0.9, -r * 1.45), (-r * 1.0, -r * 1.3), (-r * 0.2, -r * 0.85)], P(hc, fill=True))
    elif ch.hat == "straw":
        c.drawOval(skia.Rect.MakeXYWH(-r * 1.35, -r * 1.0, r * 2.7, r * 0.34), P(hc, fill=True))
        c.drawArc(skia.Rect.MakeXYWH(-r * 0.65, -r * 1.45, r * 1.3, r * 1.0), 180, 180, True, P(hc, fill=True))
        c.drawLine(-r * 0.62, -r * 0.98, r * 0.62, -r * 0.98, P((150, 60, 50), 8 * k))
    elif ch.hat == "cap":
        c.drawArc(skia.Rect.MakeXYWH(-r * 0.9, -r * 1.25, r * 1.8, r * 1.2), 180, 180, True, P(hc, fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(f * r * 0.2 - (0 if f > 0 else r * 1.1), -r * 0.72, r * 1.1, r * 0.16), 6, 6, P(hc, fill=True))
    elif ch.hat == "helmet":
        c.drawOval(skia.Rect.MakeXYWH(-r * 1.25, -r * 0.95, r * 2.5, r * 0.3), P(hc, fill=True))
        c.drawArc(skia.Rect.MakeXYWH(-r * 0.8, -r * 1.35, r * 1.6, r * 1.0), 180, 180, True, P(hc, fill=True))
    elif ch.hat == "kepi":
        c.drawRect(skia.Rect.MakeXYWH(-r * 0.7, -r * 1.5, r * 1.4, r * 0.6), P(hc, fill=True))
        c.drawRect(skia.Rect.MakeXYWH(-r * 0.7, -r * 1.0, r * 1.4, r * 0.12), P((230, 200, 90), fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(f * r * 0.1 - (0 if f > 0 else r * 0.8), -r * 0.92, r * 0.8, r * 0.12), 4, 4, P(INK, fill=True))
    if ch.hat:
        c.drawArc(skia.Rect.MakeXYWH(-r, -r, 2 * r, 2 * r), 200, 140, False, P(INK, 3 * k, alpha=0))
    c.restore()


def hand_prop(c, prop, q, k, t, f, lt):
    x, y = q
    if prop == "newspaper":
        c.save()
        c.translate(x, y)
        c.rotate(-8 * f)
        c.drawRect(skia.Rect.MakeXYWH(-70 * k, -110 * k, 140 * k, 110 * k), P((244, 240, 228), fill=True))
        c.drawRect(skia.Rect.MakeXYWH(-70 * k, -110 * k, 140 * k, 110 * k), P(INK, 3 * k))
        c.drawRect(skia.Rect.MakeXYWH(-58 * k, -100 * k, 116 * k, 22 * k), P(INK, fill=True))
        for i in range(5):
            c.drawLine(-58 * k, (-66 + i * 12) * k, 58 * k, (-66 + i * 12) * k, P((120, 120, 120), 3 * k))
        c.restore()
    elif prop == "telegram":
        c.drawRect(skia.Rect.MakeXYWH(x - 40 * k, y - 60 * k, 80 * k, 60 * k), P((240, 220, 170), fill=True))
        c.drawRect(skia.Rect.MakeXYWH(x - 40 * k, y - 60 * k, 80 * k, 60 * k), P(INK, 3 * k))
    elif prop == "suitcase":
        c.drawRoundRect(skia.Rect.MakeXYWH(x - 55 * k, y + 8 * k, 110 * k, 80 * k), 8 * k, 8 * k, P((130, 80, 45), fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(x - 55 * k, y + 8 * k, 110 * k, 80 * k), 8 * k, 8 * k, P(INK, 4 * k))
    elif prop == "binoculars":
        for d in (-1, 1):
            c.drawRoundRect(skia.Rect.MakeXYWH(x + d * 14 * k - 11 * k, y - 34 * k, 22 * k, 40 * k), 6, 6, P((40, 40, 45), fill=True))
    elif prop == "rifle":
        c.drawLine(x - f * 60 * k, y + 30 * k, x + f * 120 * k, y - 20 * k, P((110, 75, 45), 12 * k))
        c.drawLine(x + f * 60 * k, y - 4 * k, x + f * 170 * k, y - 34 * k, P((50, 50, 55), 7 * k))
    elif prop == "money":
        for i in range(3):
            c.drawRect(skia.Rect.MakeXYWH(x - 40 * k + i * 6 * k, y - 30 * k - i * 8 * k, 80 * k, 40 * k), P((100, 170, 100), fill=True))
            c.drawRect(skia.Rect.MakeXYWH(x - 40 * k + i * 6 * k, y - 30 * k - i * 8 * k, 80 * k, 40 * k), P(INK, 2.5 * k))


# --------------------------------------------------------------- world props (emus, guns, trucks...)
def emu(c, lt, x, base, s, t, facing=1, moving=False, scared=False):
    c.save()
    c.translate(x, base)
    c.scale(facing * s, s)
    ph = t * (13 if moving else 0)
    bob = 7 * math.sin(ph * 2) if moving else 3 * math.sin(t * 2.4)
    cast_shadow(c, lt, 0, 0, 220, 30, 1.2)
    for kk, off in ((0, 0), (1, math.pi)):
        sw = math.sin(ph + off) if moving else (0.12 if kk else -0.12)
        hip = (0, -200 + bob)
        knee = (24 + 34 * sw, -100)
        foot = (60 * sw, 0)
        col = (150, 125, 95) if kk == 0 else (125, 100, 80)
        c.drawLine(*hip, *knee, P(col, 12))
        c.drawLine(*knee, *foot, P(col, 10))
        c.drawLine(foot[0] - 16, 0, foot[0] + 26, 0, P(col, 8))
    body = skia.Rect.MakeXYWH(-110, -320 + bob, 215, 145)
    c.drawOval(body, skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
        [(-110, 0), (105, 0)], [rgb(lt.lit((96, 80, 72), 0.25)), rgb(lt.dark((80, 66, 60), 0.35))])))
    rnd = random.Random(3)
    for i in range(16):
        fx, fy = rnd.uniform(-95, 80), rnd.uniform(-300, -195)
        c.drawLine(fx, fy + bob, fx - 20, fy + 30 + bob, P((60, 50, 46), 5))
    c.drawOval(body, P(INK, 4, alpha=170))
    nb = 10 * math.sin(t * 3)
    lean = -40 if scared else 0
    neck = skia.Path()
    neck.moveTo(65, -280 + bob)
    neck.quadTo(110 + lean * 0.2, -380 + bob, 95 + nb + lean, -470 + bob)
    c.drawPath(neck, P((110, 130, 175), 22))
    hx, hy = 98 + nb + lean, -482 + bob
    c.drawCircle(hx, hy, 26, P((90, 80, 85), fill=True))
    c.drawLine(hx + 22, hy + 3, hx + 62, hy + 10, P((70, 60, 55), 9))
    c.drawCircle(hx + 8, hy - 6, 9 if scared else 7, P((255, 255, 255), fill=True))
    c.drawCircle(hx + 10, hy - 6, 4.5, P(INK, fill=True))
    c.restore()


def lewis_gun(c, lt, x, base, s, t, facing=1, firing=False):
    g = lambda v: v * s
    c.save()
    c.translate(x, base)
    c.scale(facing, 1)
    for d in (-1, 1):
        c.drawLine(0, -g(120), d * g(70), 0, P((70, 60, 50), g(10)))
    c.drawLine(0, -g(120), -g(40), 0, P((70, 60, 50), g(10)))
    c.drawRoundRect(skia.Rect.MakeXYWH(-g(60), -g(150), g(230), g(36)), g(14), g(14), P((60, 62, 60), fill=True))
    c.drawRect(skia.Rect.MakeXYWH(g(160), -g(140), g(90), g(14)), P((40, 40, 42), fill=True))
    c.drawOval(skia.Rect.MakeXYWH(-g(20), -g(190), g(90), g(40)), P((50, 52, 50), fill=True))  # pan magazine
    c.drawRect(skia.Rect.MakeXYWH(-g(140), -g(146), g(90), g(26)), P((120, 80, 45), fill=True))  # stock
    if firing and int(t * 22) % 2 == 0:
        glow(c, g(270), -g(133), g(80), (255, 220, 120), 230)
        poly(c, [(g(250), -g(133)), (g(330), -g(160)), (g(310), -g(133)), (g(330), -g(106))], P((255, 240, 170), fill=True))
    cast_shadow(c, lt, g(40), 0, g(260))
    c.restore()


def world_prop(c, lt, pr, t, vp):
    kind = pr.get("kind")
    z = float(pr.get("z", 0.0))
    s = float(pr.get("scale", 1.0)) * lerp(1.0, 0.35, z)
    base = lerp(FLOOR, HORIZON + 20, z * 0.9)
    x = pr["_x"]
    if kind == "emu":
        emu(c, lt, x, base, 1.15 * s, t + pr["_x0"] * 0.01, pr.get("facing", 1), pr.get("_moving", False), pr.get("scared", False))
    elif kind == "flock":
        n = int(pr.get("n", 6))
        rnd = random.Random(int(pr["_x0"]) + n)
        for i in range(n):
            zz = min(0.95, z + rnd.uniform(0, float(pr.get("spread", 0.35))))
            ss = float(pr.get("scale", 1.0)) * lerp(1.0, 0.35, zz) * 1.0
            bb = lerp(FLOOR, HORIZON + 20, zz * 0.9)
            xx = vp[0] + (x + (i - n / 2) * 170 * ss + rnd.uniform(-40, 40) - vp[0]) * lerp(1.0, 0.7, zz)
            if pr.get("scatter") and pr.get("_k", 0) > 0:
                ang = rnd.uniform(0, 2 * math.pi)
                xx += math.cos(ang) * 900 * pr["_k"] * ss
                bb += math.sin(ang) * 60 * pr["_k"]
            emu(c, lt, xx, bb, 1.15 * ss, t + i * 0.37, pr.get("facing", 1) if not pr.get("scatter") else (1 if math.cos(rnd.uniform(0, 6.28)) > 0 else -1),
                pr.get("_moving", False) or (pr.get("scatter") and pr.get("_k", 0) > 0), pr.get("scared", False))
    elif kind == "lewis_gun":
        lewis_gun(c, lt, x, base, s * 1.3, t, pr.get("facing", 1), pr.get("firing", False) and t >= float(pr.get("fire_at", 0)) and
                  t < float(pr.get("stop_at", 99)))
    elif kind == "truck":
        draw_truck(c, lt, x, base, s * 1.2, vp, t, pr.get("_moving", False))
    elif kind == "tally":  # a chalk/board tally
        fr = skia.Rect.MakeXYWH(x - 210 * s, base - 620 * s, 420 * s, 300 * s)
        c.drawRect(fr, P((40, 60, 50), fill=True))
        c.drawRect(fr, P((120, 85, 55), 14 * s))
        from .stick import typeface
        font = skia.Font(typeface(), 64 * s)
        txt = str(pr.get("text", ""))
        for i, ln in enumerate(txt.split("\n")):
            w = font.measureText(ln)
            c.drawString(ln, x - w / 2, fr.top() + (90 + 90 * i) * s, font, P((240, 240, 230), fill=True))
        c.drawLine(x, base - 320 * s, x, base, P((120, 85, 55), 14 * s))
    elif kind == "sign":
        from .stick import typeface
        font = skia.Font(typeface(), 54 * s)
        w = font.measureText(pr.get("text", "")) + 60 * s
        c.drawLine(x, base, x, base - 360 * s, P((110, 80, 55), 14 * s))
        fr = skia.Rect.MakeXYWH(x - w / 2, base - 470 * s, w, 110 * s)
        c.drawRect(fr, P((240, 225, 190), fill=True))
        c.drawRect(fr, P((110, 80, 55), 8 * s))
        c.drawString(pr.get("text", ""), x - w / 2 + 30 * s, base - 395 * s, font, P(INK, fill=True))
        cast_shadow(c, lt, x, base, 200 * s)
    elif kind == "dust":
        k = pr.get("_k", 1)
        for i in range(10):
            u = (t * 0.8 + i / 10) % 1
            c.drawCircle(x + (i - 5) * 70 + 60 * u, base - 40 - 120 * u, 40 + 70 * u, P((225, 195, 150), fill=True, alpha=int(150 * (1 - u))))
    else:
        item(c, lt, kind, x, base, s, vp, t, hexc(pr["color"]) if pr.get("color") else None)


# --------------------------------------------------------------- foreground + finishing
def foreground(c, name, lt, t, side=1):
    """A soft out-of-focus object at one edge for depth."""
    if not name:
        return
    c.saveLayer(None, skia.Paint(ImageFilter=skia.ImageFilters.Blur(14, 14)))
    x0 = W + 40 if side > 0 else -40
    if name == "wheat":
        for i in range(14):
            x = x0 - side * (i * 26)
            sway = 14 * math.sin(t * 1.6 + i)
            c.drawLine(x, H + 40, x + sway, H - 520 + (i % 4) * 60, P(lt.dark((210, 170, 80), 0.25), 18))
            c.drawOval(skia.Rect.MakeXYWH(x + sway - 16, H - 580 + (i % 4) * 60, 32, 90), P((225, 180, 80), fill=True))
    elif name == "fence_post":
        c.drawRect(skia.Rect.MakeXYWH(x0 - side * 140 - 70, H - 1050, 140, 1100), P(lt.dark((120, 90, 60), 0.4), fill=True))
    elif name == "plant":
        for i in range(8):
            a = math.radians(-60 + i * 18)
            c.drawLine(x0, H + 20, x0 - side * 420 * abs(math.sin(a)) + 20 * math.sin(t + i), H - 600 * math.cos(a) * 0.9, P((50, 90, 60), 46))
    elif name == "curtain":
        c.drawRect(skia.Rect.MakeXYWH(x0 - side * 160 - 80, -40, 160, H + 80), P(lt.dark((140, 40, 50), 0.4), fill=True))
    elif name == "lamp":
        glow(c, x0 - side * 120, 420, 260, lt.key, 200)
        c.drawCircle(x0 - side * 120, 420, 90, P((255, 230, 170), fill=True))
    elif name == "leaves":
        rnd = random.Random(4)
        for i in range(12):
            c.drawCircle(x0 - side * rnd.uniform(0, 220), rnd.uniform(-50, 500), rnd.uniform(60, 120), P((50, 90, 55), fill=True))
    c.restore()


def finish(c, lt, t):
    # warm key light from one side, cool purple shadow on the other (soft light)
    x0, x1 = (0, W) if lt.side < 0 else (W, 0)
    c.drawRect(skia.Rect.MakeWH(W, H), skia.Paint(BlendMode=skia.BlendMode.kSoftLight, Shader=skia.GradientShader.MakeLinear(
        [(x0, 0), (x1, 0)], [rgb(lt.key, 150), rgb(lt.shadow, 170)])))
    # vignette
    c.drawRect(skia.Rect.MakeWH(W, H), skia.Paint(Shader=skia.GradientShader.MakeRadial(
        (W / 2, H * 0.47), H * 0.66, [rgb((0, 0, 0), 0), rgb((0, 0, 0), 0), rgb((20, 14, 30), 175)], [0, 0.62, 1])))
