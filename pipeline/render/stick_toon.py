"""Cartoon-skit characters: big expressive heads, clothes, hair, pop-up icons.

Keeps the channel's look (shaded lilac sphere heads, colour-tinted glossy limbs and a soft glow in each
character's colour) and adds what makes skit animation read well at phone size:
- faces: eyebrows that act, glossy eyes that look at whoever is talking, many mouth shapes, blush
- bodies: a clothed torso (shirt, hoodie, vest, suit, dress, uniform) in the character's colour
- hair: short, long, bun, pigtails, spiky, curly (any colour)
- pop-up icons next to a head: ? ! anger, sweat, heart, money, idea, music, zzz, fire
"""
from __future__ import annotations

import math

import skia

from .stick import GROUND, L, W, ease_back, figure_points, lerp, paint, rgb, typeface
from .stick_disco import INK, blur, glow, mix

OUTFITS = ["shirt", "hoodie", "vest", "suit", "dress", "uniform"]
HAIRS = ["short", "long", "bun", "spiky", "pigtails", "curly"]
HAIR_COLORS = [(60, 40, 30), (25, 20, 20), (120, 70, 35), (200, 150, 70), (90, 50, 30)]


def _seed(s):
    return sum(ord(ch) * (i + 3) for i, ch in enumerate(str(s)))


def _dir(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1
    return dx / n, dy / n


def _tube(c, a, b, w, accent):
    c.drawLine(*a, *b, paint(INK, w))
    dx, dy = _dir(a, b)
    nx, ny = -dy, dx
    if nx * -0.7 + ny * -0.7 < 0:
        nx, ny = -nx, -ny
    o = w * 0.22
    c.drawLine(a[0] + nx * o, a[1] + ny * o, b[0] + nx * o, b[1] + ny * o, paint(mix(accent, (255, 255, 255), 0.6), w * 0.24, alpha=200))


# --------------------------------------------------------------- torso + clothes
def _torso(c, actor, j, r, t):
    top = j["neck"]
    hip = j["hip"]
    dx, dy = _dir(top, hip)
    nx, ny = -dy, dx
    ht, hb = r * 0.62, r * 0.56
    a = (top[0] + dx * 4, top[1] + dy * 4)
    b = (hip[0] + dx * 26, hip[1] + dy * 26)
    outfit = actor.outfit
    if outfit == "dress":
        hb = r * 0.95
    pts = [(a[0] + nx * ht, a[1] + ny * ht), (b[0] + nx * hb, b[1] + ny * hb),
           (b[0] - nx * hb, b[1] - ny * hb), (a[0] - nx * ht, a[1] - ny * ht)]
    path = skia.Path()
    path.moveTo(*pts[0])
    for p in pts[1:]:
        path.lineTo(*p)
    path.close()
    base = actor.accent if outfit not in ("suit",) else mix(actor.accent, (20, 16, 36), 0.55)
    shade = skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
        [pts[3], pts[0]], [rgb(mix(base, (255, 255, 255), 0.25)), rgb(mix(base, (0, 0, 0), 0.25))]))
    # rounded body: fill with a thick round-joined stroke of the same paint, then outline
    c.drawPath(path, shade)
    sp = skia.Paint(shade)
    sp.setStyle(skia.Paint.kStroke_Style)
    sp.setStrokeWidth(r * 0.3)
    sp.setStrokeJoin(skia.Paint.kRound_Join)
    c.drawPath(path, sp)
    ol = paint(INK, 6)
    out = skia.Path()
    # outline traced slightly outside the rounded fill
    o = r * 0.15
    q = [(pts[0][0] + nx * o, pts[0][1] + ny * o), (pts[1][0] + nx * o, pts[1][1] + ny * o),
         (pts[2][0] - nx * o, pts[2][1] - ny * o), (pts[3][0] - nx * o, pts[3][1] - ny * o)]
    out.moveTo(*q[3])
    out.quadTo(a[0] - dx * r * 0.18, a[1] - dy * r * 0.18, *q[0])
    out.lineTo(*q[1])
    out.lineTo(*q[2])
    out.close()
    c.drawPath(out, ol)
    mid = lambda k, s: (lerp(a[0], b[0], k) + nx * s, lerp(a[1], b[1], k) + ny * s)
    if outfit == "vest":  # light shirt panel down the middle, like an apron/vest
        pane = skia.Path()
        for i, (k, s) in enumerate(((0.05, -ht * 0.5), (0.05, ht * 0.5), (1.0, hb * 0.5), (1.0, -hb * 0.5))):
            (pane.moveTo if i == 0 else pane.lineTo)(*mid(k, s))
        pane.close()
        c.drawPath(pane, paint((235, 238, 228), fill=True))
        c.drawPath(pane, paint(INK, 4))
        for k in (0.35, 0.65):
            c.drawLine(*mid(k, -hb * 0.45), *mid(k, hb * 0.45), paint((180, 185, 175), 3))
    elif outfit == "hoodie":
        c.drawArc(skia.Rect.MakeXYWH(a[0] - ht * 0.8, a[1] - r * 0.25, ht * 1.6, r * 0.5), 0, 180, False, paint(mix(base, (0, 0, 0), 0.35), 10))
        for s in (-0.18, 0.18):
            p0 = mid(0.08, ht * s)
            c.drawLine(*p0, p0[0], p0[1] + r * 0.35, paint((240, 240, 240), 4))
        pk = skia.Path()
        for i, (k, s) in enumerate(((0.62, -hb * 0.55), (0.62, hb * 0.55), (0.88, hb * 0.65), (0.88, -hb * 0.65))):
            (pk.moveTo if i == 0 else pk.lineTo)(*mid(k, s))
        pk.close()
        c.drawPath(pk, paint(INK, 4))
    elif outfit == "suit":
        v = skia.Path()
        v.moveTo(*mid(0.0, -ht * 0.42))
        v.lineTo(*mid(0.42, 0))
        v.lineTo(*mid(0.0, ht * 0.42))
        v.close()
        c.drawPath(v, paint((245, 245, 245), fill=True))
        c.drawLine(*mid(0.05, 0), *mid(0.38, 0), paint(actor.accent, 12))
        for k in (0.55, 0.75):
            c.drawCircle(*mid(k, 0), 5, paint((220, 220, 230), fill=True))
    elif outfit == "uniform":
        c.drawLine(*mid(0.05, -ht), *mid(0.95, hb), paint((60, 50, 40), 10))  # strap
        c.drawRect(skia.Rect.MakeXYWH(*mid(0.25, -ht * 0.6), 26, 18), paint((240, 210, 90), fill=True))
        for k in (0.3, 0.5, 0.7):
            c.drawCircle(*mid(k, 0), 5, paint((240, 210, 90), fill=True))
    elif outfit == "shirt":
        col = skia.Path()
        col.moveTo(*mid(0.0, -ht * 0.35))
        col.lineTo(*mid(0.16, 0))
        col.lineTo(*mid(0.0, ht * 0.35))
        c.drawPath(col, paint(mix(base, (255, 255, 255), 0.55), 6))
    elif outfit == "dress":
        c.drawLine(*mid(0.4, -ht * 0.9), *mid(0.4, ht * 0.9), paint(mix(base, (255, 255, 255), 0.5), 8))


# --------------------------------------------------------------- hair
def _hair_back(c, actor, hx, hy, r):
    st, col = actor.hair, actor.hair_color
    if st == "long":
        p = skia.Path()
        p.addRoundRect(skia.Rect.MakeXYWH(hx - r * 1.12, hy - r * 0.9, r * 2.24, r * 2.15), r * 0.7, r * 0.7)
        c.drawPath(p, paint(col, fill=True))
        c.drawPath(p, paint(INK, 5))
    elif st == "pigtails":
        for s in (-1, 1):
            c.drawOval(skia.Rect.MakeXYWH(hx + s * r * 1.05 - r * 0.32, hy - r * 0.15, r * 0.64, r * 0.8), paint(col, fill=True))
            c.drawOval(skia.Rect.MakeXYWH(hx + s * r * 1.05 - r * 0.32, hy - r * 0.15, r * 0.64, r * 0.8), paint(INK, 4))
    elif st == "bun":
        c.drawCircle(hx, hy - r * 1.05, r * 0.38, paint(col, fill=True))
        c.drawCircle(hx, hy - r * 1.05, r * 0.38, paint(INK, 4))


def _hair_front(c, actor, hx, hy, r, t):
    st, col = actor.hair, actor.hair_color
    if not st or st == "none" or actor.hat in ("cap", "police", "tophat"):
        if st == "long" and actor.hat:
            pass
        return
    c.save()
    clip = skia.Path()
    clip.addCircle(hx, hy, r + 6)
    c.clipPath(clip, doAntiAlias=True)
    cut = hy - r * (0.28 if st != "spiky" else 0.35)
    p = skia.Path()
    p.moveTo(hx - r - 10, cut + r * 0.25)
    n = 7
    for i in range(n + 1):  # fringe edge
        x = hx - r + 2 * r * i / n
        y = cut + (r * 0.16 if i % 2 else 0) * (1 if st in ("short", "long", "bun", "pigtails") else 0)
        if st == "curly":
            y = cut + r * 0.1 * math.sin(i * 2.1)
        p.lineTo(x, y)
    p.lineTo(hx + r + 10, cut + r * 0.25)
    p.lineTo(hx + r + 10, hy - r - 20)
    p.lineTo(hx - r - 10, hy - r - 20)
    p.close()
    c.drawPath(p, paint(col, fill=True))
    c.restore()
    c.drawArc(skia.Rect.MakeXYWH(hx - r, hy - r, 2 * r, 2 * r), 190, 160, False, paint(INK, 6))
    if st == "spiky":
        for i in range(5):
            x = hx - r * 0.7 + i * r * 0.35
            sp = skia.Path()
            sp.moveTo(x - r * 0.18, hy - r * 0.8)
            sp.lineTo(x + r * 0.05, hy - r * 1.35 - 6 * math.sin(t * 3 + i))
            sp.lineTo(x + r * 0.2, hy - r * 0.8)
            sp.close()
            c.drawPath(sp, paint(col, fill=True))
            c.drawPath(sp, paint(INK, 4))
    if st == "curly":
        for i in range(7):
            a = math.radians(200 + i * 23)
            c.drawCircle(hx + r * 0.95 * math.cos(a), hy + r * 0.95 * math.sin(a), r * 0.22, paint(col, fill=True))


# --------------------------------------------------------------- face
BROWS = {  # (inner dy, outer dy) in head radii, + is down
    "neutral": (0, 0), "happy": (-0.04, 0.0), "excited": (-0.1, -0.06), "smug": (0.04, -0.08),
    "sad": (-0.12, 0.06), "angry": (0.14, -0.06), "shock": (-0.2, -0.18), "shocked": (-0.2, -0.18),
}


def draw_face(c, actor, hx, hy, r, t, talking, look):
    f = actor.facing
    face = actor.face or "neutral"
    cx = hx + f * r * 0.1
    ey = hy - r * 0.02
    sep = r * 0.36
    blink = (t + _seed(actor.id) * 0.37) % 3.4 < 0.11
    # eyebrows
    bi, bo = BROWS.get(face, (0, 0))
    for s in (-1, 1):
        x0 = cx + s * sep * 0.35
        x1 = cx + s * sep * 1.35
        by = ey - r * 0.36
        c.drawLine(x0, by + bi * r, x1, by + bo * r, paint(INK, r * 0.085))
    # eyes
    for s in (-1, 1):
        x = cx + s * sep
        if blink and face not in ("shock", "shocked"):
            c.drawLine(x - r * 0.12, ey, x + r * 0.12, ey, paint(INK, r * 0.06))
            continue
        if face in ("shock", "shocked"):
            c.drawCircle(x, ey, r * 0.17, paint((255, 255, 255), fill=True))
            c.drawCircle(x, ey, r * 0.17, paint(INK, r * 0.04))
            c.drawCircle(x + look * r * 0.04, ey, r * 0.06, paint(INK, fill=True))
            continue
        if face in ("happy", "excited") and talking is False and (t * 0.7) % 3 < 1.2:
            c.drawArc(skia.Rect.MakeXYWH(x - r * 0.12, ey - r * 0.08, r * 0.24, r * 0.2), 200, 140, False, paint(INK, r * 0.06))
            continue
        ew, eh = r * 0.13, r * 0.18
        if face == "angry":
            eh *= 0.8
        if face == "smug":
            eh *= 0.6
        px = x + look * r * 0.035
        c.drawOval(skia.Rect.MakeXYWH(px - ew / 2, ey - eh / 2, ew, eh), paint(INK, fill=True))
        c.drawCircle(px - ew * 0.15, ey - eh * 0.2, ew * 0.26, paint((255, 255, 255), fill=True))
    # blush
    if face in ("happy", "excited", "smug"):
        for s in (-1, 1):
            c.drawOval(skia.Rect.MakeXYWH(cx + s * sep * 1.35 - r * 0.13, ey + r * 0.2, r * 0.26, r * 0.12),
                       paint((255, 140, 160), fill=True, alpha=150))
    # mouth
    my = hy + r * 0.42
    mw = r * 0.34
    open_amt = 0.0
    if talking:
        open_amt = max(0.0, math.sin(t * 17) * 0.6 + math.sin(t * 7.3) * 0.4)
    if face in ("shock", "shocked"):
        c.drawOval(skia.Rect.MakeXYWH(cx - r * 0.12, my - r * 0.14, r * 0.24, r * 0.3), paint(INK, fill=True))
        return
    if open_amt > 0.12 or face in ("excited",):
        h = r * (0.1 + 0.22 * max(open_amt, 0.6 if face == "excited" else 0))
        p = skia.Path()
        if face in ("sad", "angry"):
            p.moveTo(cx - mw * 0.7, my + h * 0.3)
            p.quadTo(cx, my - h * 1.2, cx + mw * 0.7, my + h * 0.3)
            p.close()
        else:
            p.moveTo(cx - mw * 0.75, my - h * 0.2)
            p.lineTo(cx + mw * 0.75, my - h * 0.2)
            p.quadTo(cx + mw * 0.7, my + h, cx, my + h)
            p.quadTo(cx - mw * 0.7, my + h, cx - mw * 0.75, my - h * 0.2)
            p.close()
        c.drawPath(p, paint((60, 20, 30), fill=True))
        c.save()
        c.clipPath(p, doAntiAlias=True)
        c.drawOval(skia.Rect.MakeXYWH(cx - mw * 0.35, my + h * 0.35, mw * 0.7, h * 0.9), paint((240, 100, 110), fill=True))
        c.drawRect(skia.Rect.MakeXYWH(cx - mw, my - h * 0.3, mw * 2, h * 0.28), paint((255, 255, 255), fill=True))
        c.restore()
        c.drawPath(p, paint(INK, r * 0.04))
        return
    mp = paint(INK, r * 0.065)
    p = skia.Path()
    if face == "happy":
        p.moveTo(cx - mw * 0.6, my - r * 0.04)
        p.quadTo(cx, my + r * 0.2, cx + mw * 0.6, my - r * 0.04)
    elif face == "smug":
        p.moveTo(cx - mw * 0.5, my + r * 0.04)
        p.quadTo(cx + mw * 0.1, my + r * 0.1, cx + mw * 0.6, my - r * 0.1)
    elif face == "sad":
        p.moveTo(cx - mw * 0.5, my + r * 0.08)
        p.quadTo(cx, my - r * 0.1, cx + mw * 0.5, my + r * 0.08)
    elif face == "angry":
        c.drawRoundRect(skia.Rect.MakeXYWH(cx - mw * 0.5, my - r * 0.06, mw, r * 0.13), 6, 6, paint((255, 255, 255), fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(cx - mw * 0.5, my - r * 0.06, mw, r * 0.13), 6, 6, paint(INK, r * 0.04))
        c.drawLine(cx - mw * 0.5, my, cx + mw * 0.5, my, paint(INK, 3))
        return
    else:
        p.moveTo(cx - mw * 0.35, my)
        p.lineTo(cx + mw * 0.35, my)
    c.drawPath(p, mp)


def _glasses(c, actor, hx, hy, r):
    cx = hx + actor.facing * r * 0.1
    ey = hy - r * 0.02
    for s in (-1, 1):
        rect = skia.Rect.MakeXYWH(cx + s * r * 0.36 - r * 0.22, ey - r * 0.16, r * 0.44, r * 0.32)
        if actor.hat == "sunglasses":
            c.drawRoundRect(rect, 10, 10, paint((90, 55, 40), fill=True, alpha=235))
        c.drawRoundRect(rect, 10, 10, paint(INK, 5))
    c.drawLine(cx - r * 0.14, ey - r * 0.04, cx + r * 0.14, ey - r * 0.04, paint(INK, 5))


# --------------------------------------------------------------- whole actor
def draw_actor(c, actor, p, t, talking=False, look=None):
    from .stick import draw_hand_prop, draw_hat, star
    j = figure_points(actor, p)
    sc = actor.scale
    w = 12 * sc
    r = L["head"] * sc
    acc = actor.accent
    look = actor.facing if look is None else look
    lift = GROUND - max(j["lf"][1], j["rf"][1])
    fx = (j["lf"][0] + j["rf"][0]) / 2
    k = max(0.35, 1 - lift / 320)
    sh = paint((0, 0, 0), fill=True, alpha=int(140 * k))
    sh.setMaskFilter(blur(9))
    c.drawOval(skia.Rect.MakeXYWH(fx - 120 * k, GROUND - 12, 240 * k, 30), sh)
    # soft glow in the character's colour (the channel look)
    g = glow(acc, w + 22, 14, 110)
    for a_, b_ in (("hip", "lk"), ("lk", "lf"), ("hip", "rk"), ("rk", "rf"), ("sh", "le"), ("le", "lh"), ("sh", "re"), ("re", "rh"), ("hip", "neck")):
        c.drawLine(*j[a_], *j[b_], g)
    hx, hy = j["head"]
    c.drawCircle(hx, hy, r + 12, glow(acc, 0, 16, 100, fill=True))
    # back leg + back arm
    _tube(c, j["hip"], j["lk"], w, acc)
    _tube(c, j["lk"], j["lf"], w, acc)
    c.drawOval(skia.Rect.MakeXYWH(j["lf"][0] - 6 + actor.facing * 10 - 16, j["lf"][1] - 10, 38, 18), paint(INK, fill=True))
    _tube(c, j["sh"], j["le"], w, acc)
    _tube(c, j["le"], j["lh"], w, acc)
    c.drawCircle(*j["lh"], w * 0.85, paint(INK, fill=True))
    _tube(c, j["hip"], j["rk"], w, acc)
    _tube(c, j["rk"], j["rf"], w, acc)
    c.drawOval(skia.Rect.MakeXYWH(j["rf"][0] - 6 + actor.facing * 10 - 16, j["rf"][1] - 10, 38, 18), paint(INK, fill=True))
    _hair_back(c, actor, hx, hy, r)
    _torso(c, actor, j, r, t)
    # front arm over the body, under the head (raised arms never cover the face)
    _tube(c, j["sh"], j["re"], w, acc)
    _tube(c, j["re"], j["rh"], w, acc)
    c.drawCircle(*j["rh"], w * 0.85, paint(INK, fill=True))
    # head: shaded sphere, ink outline, colour rim light
    shade = skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeRadial(
        (hx - r * 0.35, hy - r * 0.4), r * 1.55,
        [rgb((255, 255, 255)), rgb((236, 230, 248)), rgb((185, 172, 222))], [0, 0.45, 1]))
    c.drawCircle(hx, hy, r, shade)
    c.drawArc(skia.Rect.MakeXYWH(hx - r + 5, hy - r + 5, 2 * r - 10, 2 * r - 10), -10, 110, False, paint(acc, r * 0.07, alpha=200))
    c.drawCircle(hx, hy, r, paint(INK, 6.5))
    c.drawOval(skia.Rect.MakeXYWH(hx - r * 0.66, hy - r * 0.74, r * 0.36, r * 0.2), paint((255, 255, 255), fill=True, alpha=220))
    _hair_front(c, actor, hx, hy, r, t)
    draw_face(c, actor, hx, hy, r, t, talking, look)
    if actor.hat in ("sunglasses", "glasses"):
        _glasses(c, actor, hx, hy, r)
    elif actor.hat:
        draw_hat(c, actor, j, r)
    # a hand raised in front of the face still shows (e.g. facepalm, waving) as a small fist
    if j["rh"][1] < hy + r and math.hypot(j["rh"][0] - hx, j["rh"][1] - hy) < r:
        c.drawCircle(*j["rh"], w * 0.95, paint(INK, fill=True))
    if actor.prop:
        draw_hand_prop(c, actor, j, t)
    if actor.stars:
        x0 = min(max(hx - 160, 40), W - 40 - 5 * 64)
        for i in range(6):
            on = i < actor.stars
            star(c, x0 + i * 64, hy - r - 70, 26, (255, 221, 51) if on and int(t * 4) % 2 == 0 else
                 ((255, 255, 255) if on else (90, 90, 110)), outline=INK)
    return j


# --------------------------------------------------------------- pop-up icons (screen space)
def _txt(c, s, x, y, size, color, stroke=True):
    font = skia.Font(typeface(), size)
    w = font.measureText(s)
    if stroke:
        c.drawString(s, x - w / 2, y + size * 0.35, font, paint(INK, size * 0.14))
    c.drawString(s, x - w / 2, y + size * 0.35, font, paint(color, fill=True))


def draw_icon(c, icon, x, y, s, t):
    """Draw one icon centred at (x, y); s = size in px."""
    if icon == "?":
        _txt(c, "?", x, y, s * 1.3, (255, 255, 255))
    elif icon == "!":
        _txt(c, "!", x, y, s * 1.4, (255, 221, 51))
    elif icon == "anger":
        for a in range(4):
            c.save()
            c.translate(x, y)
            c.rotate(a * 90 + 45)
            p = skia.Path()
            p.moveTo(s * 0.12, s * 0.45)
            p.quadTo(s * 0.12, s * 0.12, s * 0.45, s * 0.12)
            c.drawPath(p, paint((230, 30, 50), s * 0.13))
            c.restore()
    elif icon == "sweat":
        for i, (dx, dy, k) in enumerate(((0, 0, 1), (s * 0.45, s * 0.35, 0.7))):
            p = skia.Path()
            p.moveTo(x + dx, y + dy - s * 0.4 * k)
            p.quadTo(x + dx + s * 0.32 * k, y + dy + s * 0.1 * k, x + dx, y + dy + s * 0.3 * k)
            p.quadTo(x + dx - s * 0.32 * k, y + dy + s * 0.1 * k, x + dx, y + dy - s * 0.4 * k)
            c.drawPath(p, paint((110, 190, 255), fill=True))
            c.drawPath(p, paint(INK, 3))
    elif icon == "heart":
        p = skia.Path()
        r = s * 0.42
        p.moveTo(x, y + r)
        p.cubicTo(x - 2 * r, y - 0.2 * r, x - r, y - 1.4 * r, x, y - 0.5 * r)
        p.cubicTo(x + r, y - 1.4 * r, x + 2 * r, y - 0.2 * r, x, y + r)
        c.drawPath(p, paint((255, 70, 110), fill=True))
        c.drawPath(p, paint(INK, 4))
    elif icon == "money":
        c.save()
        c.translate(x, y)
        c.rotate(-12 + 6 * math.sin(t * 5))
        c.drawRoundRect(skia.Rect.MakeXYWH(-s * 0.6, -s * 0.32, s * 1.2, s * 0.64), 6, 6, paint((90, 200, 100), fill=True))
        c.drawRoundRect(skia.Rect.MakeXYWH(-s * 0.6, -s * 0.32, s * 1.2, s * 0.64), 6, 6, paint(INK, 4))
        _txt(c, "$", 0, 0, s * 0.5, (30, 110, 40), stroke=False)
        c.restore()
    elif icon == "idea":
        c.drawCircle(x, y, s * 0.55, glow((255, 240, 120), 0, 14, 180, fill=True))
        c.drawCircle(x, y - s * 0.08, s * 0.36, paint((255, 230, 90), fill=True))
        c.drawCircle(x, y - s * 0.08, s * 0.36, paint(INK, 4))
        c.drawRect(skia.Rect.MakeXYWH(x - s * 0.16, y + s * 0.26, s * 0.32, s * 0.2), paint((150, 150, 160), fill=True))
    elif icon == "music":
        for i in range(2):
            xx, yy = x + i * s * 0.45, y - i * s * 0.2 + 6 * math.sin(t * 4 + i)
            c.drawOval(skia.Rect.MakeXYWH(xx - s * 0.18, yy + s * 0.18, s * 0.3, s * 0.22), paint((150, 90, 255), fill=True))
            c.drawLine(xx + s * 0.1, yy + s * 0.26, xx + s * 0.1, yy - s * 0.35, paint((150, 90, 255), 5))
    elif icon == "zzz":
        for i in range(3):
            _txt(c, "Z", x + i * s * 0.32, y - i * s * 0.32, s * (0.5 + 0.15 * i), (255, 255, 255))
    elif icon == "fire":
        p = skia.Path()
        f = 1 + 0.08 * math.sin(t * 12)
        p.moveTo(x, y - s * 0.6 * f)
        p.quadTo(x + s * 0.55, y, x + s * 0.3, y + s * 0.4)
        p.quadTo(x, y + s * 0.55, x - s * 0.3, y + s * 0.4)
        p.quadTo(x - s * 0.55, y, x, y - s * 0.6 * f)
        c.drawPath(p, paint((255, 120, 30), fill=True))
        c.drawPath(p, paint(INK, 4))
    elif icon == "skull":
        c.drawCircle(x, y, s * 0.4, paint((245, 245, 245), fill=True))
        c.drawCircle(x, y, s * 0.4, paint(INK, 4))
        for d in (-1, 1):
            c.drawCircle(x + d * s * 0.15, y - s * 0.02, s * 0.1, paint(INK, fill=True))


AUTO_ICON = {"angry": "anger", "shock": "!", "shocked": "!", "sad": "sweat"}
ACTION_ICON = {"think": "?", "facepalm": "sweat", "cry": "sweat", "laugh": "music", "count_money": "money",
               "lie": "zzz", "celebrate": "heart", "angry": "anger"}


def draw_pops(c, pops, t, head_screen):
    """pops: list of (start, actor_id, icon). head_screen: id -> (x, y, r) in screen space."""
    for start, aid, icon in pops:
        lt = t - start
        if lt < 0 or lt > 1.6 or aid not in head_screen:
            continue
        x, y, r = head_screen[aid]
        k = ease_back(min(1, lt / 0.22))
        fade = 1 if lt < 1.3 else max(0, 1 - (lt - 1.3) / 0.3)
        if fade <= 0:
            continue
        s = max(60, r * 0.75) * k
        px = min(W - 70, max(70, x + r * 0.95))
        py = max(230, y - r * 0.95) - 8 * math.sin(lt * 4)
        c.saveLayerAlpha(None, int(255 * fade))
        draw_icon(c, icon, px, py, s, t)
        c.restore()
