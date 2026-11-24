"""Disco look for the stickman world: the style lives in the animation, not in UI boxes.

- Figures: glossy 3D-shaded tube limbs, sphere heads with a specular highlight, a neon glow
  in each character's colour that pulses on the beat, and a soft floor shadow.
- World: light-up dance floor (indoor sets), sweeping spotlight beams, disco-ball sparkles and a
  pink/purple colour grade applied to every set, including the outdoor story sets.
- Extra sets for true stories: town (old European square), field, ocean (ship deck at night),
  paris, forest (storm + watchtower), stadium. Extra props: emu, disco_ball. Extra fx: lightning, rain, confetti.
"""
from __future__ import annotations

import math
import random

import skia

from .stick import GROUND, H, L, SETTINGS, W, _grad, draw_palm, figure_points, lerp, paint, rgb, setting

BPM = 120
DISCO = [(255, 46, 120), (255, 150, 40), (150, 70, 255), (0, 210, 230)]
INK = (26, 16, 46)
INDOOR = {"stage", "void", "room", "gaming", "news_desk"}
OUTDOOR_DAY = {"city_day", "beach", "field", "stadium"}


def beat(t):
    """0..1 pulse that peaks on each beat."""
    return math.exp(-((t * BPM / 60) % 1) * 5)


def blur(sigma):
    return skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, sigma)


def glow(color, width, sigma, alpha, fill=False):
    p = paint(color, width, fill=fill, alpha=alpha)
    p.setMaskFilter(blur(sigma))
    return p


def mix(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


# --------------------------------------------------------------- figures
def _tube(c, a, b, w, base, accent):
    """A limb drawn as a lit 3D tube: dark core, white highlight toward the top-left light, coloured rim."""
    c.drawLine(*a, *b, paint(base, w))
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1
    nx, ny = -dy / n, dx / n
    if nx * -0.7 + ny * -0.7 < 0:
        nx, ny = -nx, -ny
    o = w * 0.24
    c.drawLine(a[0] + nx * o, a[1] + ny * o, b[0] + nx * o, b[1] + ny * o,
               paint(mix(accent, (255, 255, 255), 0.65), w * 0.26, alpha=210))
    c.drawLine(a[0] - nx * o, a[1] - ny * o, b[0] - nx * o, b[1] - ny * o, paint(accent, w * 0.22, alpha=230))


BACK = (("hip", "lk"), ("lk", "lf"), ("sh", "le"), ("le", "lh"))
FRONT = (("hip", "rk"), ("rk", "rf"), ("sh", "re"), ("re", "rh"))


def draw_actor(c, actor, p, t, talking=False):
    from .stick import draw_face, draw_hand_prop, draw_hat, star
    j = figure_points(actor, p)
    w = 15 * actor.scale
    r = L["head"] * actor.scale
    acc = actor.accent
    # floor shadow (shrinks as the figure jumps)
    lift = GROUND - max(j["lf"][1], j["rf"][1])
    fx = (j["lf"][0] + j["rf"][0]) / 2
    k = max(0.35, 1 - lift / 320)
    sh = paint((0, 0, 0), fill=True, alpha=int(160 * k))
    sh.setMaskFilter(blur(9))
    c.drawOval(skia.Rect.MakeXYWH(fx - 120 * k, GROUND - 12, 240 * k, 30), sh)
    # neon glow that pulses on the beat
    pulse = 0.7 + 0.3 * beat(t)
    g = glow(acc, w + 30, 18, int(190 * pulse))
    for a, b in BACK + FRONT + (("hip", "neck"),):
        c.drawLine(*j[a], *j[b], g)
    c.drawCircle(*j["head"], r + 14, glow(acc, 0, 20, int(200 * pulse), fill=True))
    # limbs as tubes, back side slightly lighter for depth
    for a, b in BACK:
        _tube(c, j[a], j[b], w, (60, 42, 96), acc)
    _tube(c, j["hip"], j["neck"], w * 1.15, INK, acc)
    # shirt stripe: a glossy accent band on the torso
    p0 = (lerp(j["hip"][0], j["neck"][0], 0.22), lerp(j["hip"][1], j["neck"][1], 0.22))
    p1 = (lerp(j["hip"][0], j["neck"][0], 0.78), lerp(j["hip"][1], j["neck"][1], 0.78))
    c.drawLine(*p0, *p1, paint(acc, w * 0.75))
    c.drawLine(p0[0] - 3, p0[1], p1[0] - 3, p1[1], paint(mix(acc, (255, 255, 255), 0.6), w * 0.2, alpha=220))
    for a, b in FRONT:
        _tube(c, j[a], j[b], w, INK, acc)
    # sphere head: radial shading + specular highlight + coloured rim light
    hx, hy = j["head"]
    shade = skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeRadial(
        (hx - r * 0.35, hy - r * 0.4), r * 1.55,
        [rgb((255, 255, 255)), rgb((238, 230, 252)), rgb((178, 160, 220))], [0, 0.45, 1]))
    c.drawCircle(hx, hy, r, shade)
    c.drawCircle(hx, hy, r, paint(INK, w * 0.55))
    c.drawArc(skia.Rect.MakeXYWH(hx - r + 4, hy - r + 4, 2 * r - 8, 2 * r - 8), -10, 120, False, paint(acc, w * 0.35, alpha=235))
    c.drawOval(skia.Rect.MakeXYWH(hx - r * 0.62, hy - r * 0.72, r * 0.42, r * 0.26), paint((255, 255, 255), fill=True, alpha=235))
    draw_face(c, actor, j, t, talking)
    draw_hat(c, actor, j, r)
    if actor.prop:
        draw_hand_prop(c, actor, j, t)
    if actor.stars:
        x0 = min(max(hx - 160, 40), W - 40 - 5 * 64)
        for i in range(6):
            on = i < actor.stars
            star(c, x0 + i * 64, hy - r - 70, 26, DISCO[i % 2] if on and int(t * 4) % 2 == 0 else
                 ((255, 255, 255) if on else (90, 90, 110)), outline=INK)
    return j


# --------------------------------------------------------------- world lighting
def disco_floor(c, t):
    """Light-up dance floor in fake perspective, tiles flashing on the beat."""
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, H), paint((18, 10, 34), fill=True))
    b = int(t * BPM / 60)
    vx = 540
    rows = [GROUND]
    hgt = 46
    while rows[-1] < H + 200:
        rows.append(rows[-1] + hgt)
        hgt *= 1.22
    sc = lambda y: 1 + (y - GROUND) / 260
    for r in range(len(rows) - 1):
        y0, y1 = rows[r], rows[r + 1]
        for i in range(-12, 14):
            xa0, xa1 = vx + (i * 120 - 60) * sc(y0), vx + ((i + 1) * 120 - 60) * sc(y0)
            xb0, xb1 = vx + (i * 120 - 60) * sc(y1), vx + ((i + 1) * 120 - 60) * sc(y1)
            if xb1 < -200 or xb0 > W + 200:
                continue
            lit = random.Random(i * 97 + r * 13 + b * 7).random() < 0.38
            col = DISCO[(i + r + b) % 4] if lit else (40, 24, 70)
            tile = skia.Path()
            tile.moveTo(xa0 + 3, y0 + 3)
            tile.lineTo(xa1 - 3, y0 + 3)
            tile.lineTo(xb1 - 3, y1 - 3)
            tile.lineTo(xb0 + 3, y1 - 3)
            tile.close()
            a = int(150 + 90 * beat(t)) if lit else 255
            c.drawPath(tile, paint(col, fill=True, alpha=a))
            if lit:
                c.drawPath(tile, glow(col, 0, 10, 120, fill=True))
    c.drawLine(-400, GROUND, W + 400, GROUND, glow((255, 120, 200), 10, 6, 230))
    c.drawLine(-400, GROUND, W + 400, GROUND, paint((255, 220, 240), 3))


def neon_edge(c, color=(255, 70, 160)):
    c.drawLine(-400, GROUND, W + 400, GROUND, glow(color, 12, 8, 200))
    c.drawLine(-400, GROUND, W + 400, GROUND, paint(mix(color, (255, 255, 255), 0.6), 3))


def disco_ball(c, x, y, r, t):
    c.drawLine(x, -100, x, y - r, paint((200, 200, 220), 4))
    c.drawCircle(x, y, r + 30, glow((255, 255, 255), 0, 30, 90, fill=True))
    c.save()
    clip = skia.Path()
    clip.addCircle(x, y, r)
    c.clipPath(clip, doAntiAlias=True)
    c.drawCircle(x, y, r, paint((150, 150, 175), fill=True))
    rot = t * 1.4
    f = r / 5
    for row in range(-6, 7):
        yy = y + row * f
        for col in range(-8, 9):
            xx = x + ((col + rot) % 16 - 8) * f
            v = random.Random(row * 31 + (col + int(rot)) * 7).random()
            shade = int(120 + 135 * v)
            cc = DISCO[(row + col) % 4] if v > 0.92 else (shade, shade, min(255, shade + 20))
            c.drawRect(skia.Rect.MakeXYWH(xx + 1.5, yy + 1.5, f - 3, f - 3), paint(cc, fill=True))
    hl = skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeRadial((x - r * 0.4, y - r * 0.45), r * 1.4,
                                                                         [rgb((255, 255, 255), 110), rgb((0, 0, 0), 120)]))
    c.drawCircle(x, y, r, hl)
    c.restore()


def beams(c, t, strength=1.0):
    """Sweeping spotlight beams from above, added on top of the set."""
    if strength <= 0:
        return
    for i, (ox, col) in enumerate(((140, DISCO[0]), (540, DISCO[3]), (940, DISCO[1]))):
        ang = math.radians(math.sin(t * 0.9 + i * 2.1) * 28)
        L_ = 1900
        spread = math.radians(9)
        p = skia.Path()
        p.moveTo(ox, -60)
        p.lineTo(ox + L_ * math.sin(ang - spread), -60 + L_ * math.cos(ang - spread))
        p.lineTo(ox + L_ * math.sin(ang + spread), -60 + L_ * math.cos(ang + spread))
        p.close()
        sp = skia.Paint(AntiAlias=True, BlendMode=skia.BlendMode.kScreen, Shader=skia.GradientShader.MakeLinear(
            [(ox, -60), (ox + L_ * math.sin(ang), L_ * math.cos(ang))],
            [rgb(col, int(150 * strength)), rgb(col, 0)]))
        sp.setMaskFilter(blur(14))
        c.drawPath(p, sp)


def sparkles(c, t, n=36, strength=1.0):
    """Disco-ball reflections drifting across the scene."""
    if strength <= 0:
        return
    rnd = random.Random(11)
    for i in range(n):
        x = (rnd.uniform(0, W) + t * rnd.uniform(30, 90)) % (W + 80) - 40
        y = rnd.uniform(120, GROUND + 300)
        tw = 0.5 + 0.5 * math.sin(t * rnd.uniform(3, 7) + i)
        col = rnd.choice([(255, 255, 255), DISCO[0], DISCO[1], DISCO[3]])
        s = rnd.uniform(4, 9) * (0.6 + 0.6 * tw)
        a = int(220 * tw * strength)
        c.drawCircle(x, y, s * 2.4, glow(col, 0, 6, a // 2, fill=True))
        d = skia.Path()
        d.moveTo(x, y - s * 1.6)
        d.lineTo(x + s * 0.5, y)
        d.lineTo(x, y + s * 1.6)
        d.lineTo(x - s * 0.5, y)
        d.close()
        c.drawPath(d, paint(col, fill=True, alpha=a))


def grade(c, setting_name):
    """Pink-to-purple soft-light grade so every set shares the channel's palette."""
    k = 0.75 if setting_name in OUTDOOR_DAY else 1.0
    gp = skia.Paint(BlendMode=skia.BlendMode.kSoftLight, Shader=skia.GradientShader.MakeLinear(
        [(0, 0), (0, H)], [rgb((255, 60, 150), int(200 * k)), rgb((255, 140, 60), int(140 * k)), rgb((90, 40, 200), int(220 * k))],
        [0, 0.5, 1]))
    c.drawRect(skia.Rect.MakeXYWH(-400, -400, W + 800, H + 800), gp)


def world_pass(c, setting_name, t):
    """Called after the set is drawn, before props and actors."""
    if setting_name in INDOOR:
        disco_floor(c, t)
    else:
        neon_edge(c)
    grade(c, setting_name)
    day = setting_name in OUTDOOR_DAY
    beams(c, t, 0.45 if day else 1.0)
    sparkles(c, t, 26 if day else 40, 0.6 if day else 1.0)
    if setting_name in ("stage", "void", "room", "gaming"):
        disco_ball(c, 860, 470, 62, t)


# --------------------------------------------------------------- restyled built-in sets
@setting("city_day")
def _city_day(c, t, cam):
    _grad(c, (255, 110, 160), (255, 205, 140))
    c.drawCircle(540 - cam * 0.2, 820, 210, paint((255, 235, 170), fill=True, alpha=230))
    rnd = random.Random(5)
    x = -300
    while x < W + 300:
        bw, bh = rnd.randint(120, 230), rnd.randint(300, 700)
        col = rnd.choice([(120, 60, 150), (150, 70, 160), (100, 50, 130)])
        c.drawRect(skia.Rect.MakeXYWH(x - cam * 0.4, GROUND - bh, bw, bh), paint(col, fill=True))
        x += bw + rnd.randint(8, 30)
    _street(c, (70, 40, 90))


@setting("void")
def _void(c, t, cam):
    _grad(c, (30, 12, 60), (80, 20, 110), 0, GROUND)
    for yy in range(160, GROUND, 60):
        for xx in range(30, W, 60):
            c.drawCircle(xx, yy, 2.5, paint((255, 255, 255), fill=True, alpha=40))


@setting("room")
def _room(c, t, cam):
    _grad(c, (60, 26, 96), (110, 40, 130), -400, GROUND)
    c.drawRoundRect(skia.Rect.MakeXYWH(640 - cam * 0.3, 640, 300, 330), 10, 10, paint((40, 20, 80), fill=True))
    for i in range(6):
        c.drawRect(skia.Rect.MakeXYWH(660 - cam * 0.3 + i * 48, 860 - (i * 37) % 120, 30, 110 + (i * 37) % 120),
                   paint((90, 50, 140), fill=True))
    c.drawRoundRect(skia.Rect.MakeXYWH(640 - cam * 0.3, 640, 300, 330), 10, 10, paint((255, 90, 180), 8))
    c.drawLine(-400, 560, W + 400, 560, glow((255, 80, 170), 10, 10, 220))
    c.drawLine(-400, 560, W + 400, 560, paint((255, 210, 235), 3))
    c.drawRoundRect(skia.Rect.MakeXYWH(80 - cam * 0.5, 820, 240, 160), 12, 12, paint((255, 140, 60), fill=True))


@setting("news_desk")
def _news(c, t, cam):
    _grad(c, (40, 14, 80), (130, 30, 120))
    for i in range(12):
        c.drawLine(-200 + i * 120 - cam * 0.2, 200, -500 + i * 160 - cam * 0.2, GROUND, paint((255, 90, 180), 3, alpha=70))
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND - 330, W + 800, 60), paint((255, 46, 120), fill=True))
    from .stick import draw_text_center
    draw_text_center(c, "BREAKING NEWS", 300, GROUND - 300, 46, (255, 255, 255), 600)


def _street(c, fill):
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, H), paint(fill, fill=True))
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, 60), paint(mix(fill, (255, 255, 255), 0.12), fill=True))
    for i in range(-6, 16):
        c.drawRect(skia.Rect.MakeXYWH(i * 160, GROUND + 190, 90, 14), paint((255, 210, 120), fill=True, alpha=170))


# --------------------------------------------------------------- new story sets
@setting("town")
def _town(c, t, cam):
    """An old European town square (half-timbered houses, cathedral spire), at dusk."""
    _grad(c, (60, 24, 110), (255, 120, 120))
    sp = skia.Path()  # cathedral spire silhouette
    sx = 760 - cam * 0.15
    sp.moveTo(sx - 120, GROUND - 300)
    sp.lineTo(sx - 120, GROUND - 900)
    sp.lineTo(sx - 40, GROUND - 980)
    sp.lineTo(sx, GROUND - 1290)
    sp.lineTo(sx + 40, GROUND - 980)
    sp.lineTo(sx + 120, GROUND - 900)
    sp.lineTo(sx + 120, GROUND - 300)
    sp.close()
    c.drawPath(sp, paint((70, 30, 100), fill=True))
    rnd = random.Random(8)
    x = -320
    while x < W + 300:
        bw, bh = rnd.randint(190, 250), rnd.randint(420, 560)
        xx = x - cam * 0.4
        wall = rnd.choice([(245, 220, 185), (240, 200, 170), (230, 210, 200)])
        c.drawRect(skia.Rect.MakeXYWH(xx, GROUND - bh, bw, bh), paint(wall, fill=True))
        roof = skia.Path()
        roof.moveTo(xx - 14, GROUND - bh)
        roof.lineTo(xx + bw / 2, GROUND - bh - 170)
        roof.lineTo(xx + bw + 14, GROUND - bh)
        roof.close()
        c.drawPath(roof, paint(rnd.choice([(150, 40, 70), (120, 40, 90), (170, 60, 60)]), fill=True))
        beam = paint((80, 40, 50), 10, cap=False)
        for fy in range(GROUND - bh, GROUND, 140):
            c.drawLine(xx, fy, xx + bw, fy, beam)
            c.drawLine(xx, fy, xx + bw / 2, fy + 140, beam)
            c.drawLine(xx + bw, fy, xx + bw / 2, fy + 140, beam)
        c.drawRect(skia.Rect.MakeXYWH(xx, GROUND - bh, bw, bh), paint((80, 40, 50), 10))
        for wy in range(GROUND - bh + 40, GROUND - 120, 140):
            c.drawRect(skia.Rect.MakeXYWH(xx + 24, wy, 40, 54), paint((255, 210, 110), fill=True))
            c.drawRect(skia.Rect.MakeXYWH(xx + bw - 64, wy, 40, 54), paint((255, 210, 110), fill=True))
        x += bw + 6
    # cobblestones
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, H), paint((95, 70, 100), fill=True))
    rnd = random.Random(2)
    for yy in range(GROUND + 10, H, 46):
        off = (yy // 46) % 2 * 40
        for xx in range(-80 + off, W + 80, 80):
            c.drawRoundRect(skia.Rect.MakeXYWH(xx - cam * 0.8, yy, 70, 36), 14, 14,
                            paint(rnd.choice([(120, 90, 125), (110, 82, 118), (130, 100, 135)]), fill=True))


@setting("field")
def _field(c, t, cam):
    """Open farmland at sunset: hills, wheat, a wire fence."""
    _grad(c, (255, 100, 140), (255, 200, 130))
    c.drawCircle(300 - cam * 0.1, 980, 160, paint((255, 235, 170), fill=True, alpha=230))
    for i, (cx, col) in enumerate(((150, (150, 70, 140)), (700, (130, 60, 130)), (1150, (150, 70, 140)))):
        c.drawOval(skia.Rect.MakeXYWH(cx - 520 - cam * 0.2, 1020, 1040, 420), paint(col, fill=True))
    c.drawRect(skia.Rect.MakeXYWH(-400, 1160, W + 800, GROUND - 1160), paint((235, 160, 60), fill=True))
    rnd = random.Random(4)
    for i in range(140):
        x = rnd.uniform(-100, W + 100) - cam * 0.6
        y = rnd.uniform(1170, GROUND)
        sway = 6 * math.sin(t * 2 + i)
        c.drawLine(x, y, x + sway, y - 34, paint((255, 205, 90), 4))
    for i in range(-2, 9):
        px = i * 170 - cam * 0.8
        c.drawLine(px, GROUND - 150, px, GROUND, paint((90, 50, 50), 12))
    for fy in (GROUND - 130, GROUND - 80):
        c.drawLine(-400, fy, W + 400, fy, paint((70, 40, 50), 3))
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, H), paint((150, 90, 70), fill=True))
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, 50), paint((175, 110, 80), fill=True))


def _ship(c, x, y, s):
    """Four-funnel liner silhouette (Olympic class)."""
    c.save()
    c.translate(x, y)
    c.scale(s, s)
    hull = skia.Path()
    hull.moveTo(-500, -40)
    hull.lineTo(520, -40)
    hull.lineTo(470, 60)
    hull.lineTo(-460, 60)
    hull.close()
    c.drawPath(hull, paint((25, 15, 40), fill=True))
    c.drawRect(skia.Rect.MakeXYWH(-400, -110, 780, 70), paint((240, 235, 230), fill=True))
    for i in range(4):
        fx = -260 + i * 170
        c.drawRect(skia.Rect.MakeXYWH(fx, -260, 64, 150), paint((225, 160, 70), fill=True))
        c.drawRect(skia.Rect.MakeXYWH(fx, -260, 64, 34), paint((25, 15, 40), fill=True))
    for i in range(24):
        c.drawCircle(-380 + i * 32, -75, 6, paint((255, 220, 120), fill=True))
    c.restore()


@setting("ocean")
def _ocean(c, t, cam):
    """Night at sea seen from a ship's deck, a sister ship on the horizon."""
    _grad(c, (14, 8, 44), (90, 30, 120), 0, 1000)
    rnd = random.Random(9)
    for i in range(70):
        c.drawCircle(rnd.uniform(0, W), rnd.uniform(120, 900), rnd.uniform(1.5, 3.5),
                     paint((255, 255, 255), fill=True, alpha=int(120 + 120 * abs(math.sin(t * 2 + i)))))
    c.drawCircle(250 - cam * 0.1, 360, 70, paint((255, 240, 220), fill=True))
    c.drawRect(skia.Rect.MakeXYWH(-400, 1000, W + 800, GROUND - 1000), paint((20, 30, 80), fill=True))
    for i in range(8):
        y = 1015 + i * 34
        off = math.sin(t * 1.6 + i) * 40
        c.drawLine(-100 + off, y, W + 100 + off, y, paint((120, 90, 220), 3, alpha=120))
    _ship(c, 760 - cam * 0.3, 1000, 0.42)
    # deck railing + planks
    for i in range(-3, 16):
        px = i * 90 - cam * 0.8
        c.drawLine(px, GROUND - 170, px, GROUND, paint((240, 235, 230), 8))
    c.drawLine(-400, GROUND - 170, W + 400, GROUND - 170, paint((240, 235, 230), 12))
    c.drawLine(-400, GROUND - 90, W + 400, GROUND - 90, paint((240, 235, 230), 6))
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, H), paint((140, 90, 70), fill=True))
    for yy in range(GROUND + 30, H, 50):
        c.drawLine(-400, yy, W + 400, yy, paint((110, 70, 55), 4))


def _eiffel(c, x, base, s, t):
    c.save()
    c.translate(x, base)
    c.scale(s, s)
    col = (40, 20, 70)
    p = skia.Path()
    p.moveTo(-230, 0)
    p.quadTo(-120, -300, -40, -700)
    p.lineTo(-14, -1100)
    p.lineTo(14, -1100)
    p.lineTo(40, -700)
    p.quadTo(120, -300, 230, 0)
    p.lineTo(140, 0)
    p.quadTo(0, -230, -140, 0)
    p.close()
    c.drawPath(p, paint(col, fill=True))
    for yy, ww in ((-330, 170), (-700, 90)):
        c.drawRect(skia.Rect.MakeXYWH(-ww, yy - 18, 2 * ww, 36), paint(col, fill=True))
    c.drawLine(0, -1100, 0, -1200, paint(col, 10))
    rnd = random.Random(int(t * 6))
    for i in range(30):  # sparkle lights
        yy = -rnd.uniform(0, 1100)
        ww = 200 * (1 + yy / 1100) * 0.9 + 20
        c.drawCircle(rnd.uniform(-ww, ww), yy, 4, paint((255, 235, 170), fill=True, alpha=230))
    c.drawCircle(0, -1150, 18, glow((255, 220, 160), 0, 12, 230, fill=True))
    c.restore()


@setting("paris")
def _paris(c, t, cam):
    _grad(c, (40, 16, 90), (255, 110, 150))
    _eiffel(c, 700 - cam * 0.25, GROUND - 120, 0.95, t)
    rnd = random.Random(6)
    x = -300
    while x < W + 300:
        bw, bh = rnd.randint(150, 240), rnd.randint(240, 380)
        xx = x - cam * 0.5
        c.drawRect(skia.Rect.MakeXYWH(xx, GROUND - bh, bw, bh), paint((70, 36, 100), fill=True))
        roof = skia.Path()
        roof.moveTo(xx, GROUND - bh)
        roof.lineTo(xx + 30, GROUND - bh - 60)
        roof.lineTo(xx + bw - 30, GROUND - bh - 60)
        roof.lineTo(xx + bw, GROUND - bh)
        roof.close()
        c.drawPath(roof, paint((50, 26, 80), fill=True))
        for wy in range(GROUND - bh + 30, GROUND - 60, 80):
            for wx in range(int(xx) + 20, int(xx) + bw - 40, 55):
                if rnd.random() < 0.55:
                    c.drawRect(skia.Rect.MakeXYWH(wx, wy, 26, 40), paint((255, 210, 120), fill=True))
        x += bw + 4
    _street(c, (60, 34, 80))


@setting("forest")
def _forest(c, t, cam):
    """Mountain forest under a storm, with a fire lookout tower."""
    _grad(c, (24, 18, 54), (110, 60, 130))
    for i, (cx, col) in enumerate(((-100, (60, 40, 100)), (500, (70, 45, 110)), (1100, (60, 40, 100)))):
        m = skia.Path()
        m.moveTo(cx - 600 - cam * 0.15, GROUND - 200)
        m.lineTo(cx - cam * 0.15, GROUND - 820 + i * 60)
        m.lineTo(cx + 600 - cam * 0.15, GROUND - 200)
        m.close()
        c.drawPath(m, paint(col, fill=True))
    tx = 820 - cam * 0.35  # lookout tower
    for dx in (-70, 70):
        c.drawLine(tx + dx * 1.4, GROUND - 60, tx + dx * 0.6, GROUND - 640, paint((60, 30, 50), 12))
    for yy in range(GROUND - 600, GROUND - 60, 110):
        c.drawLine(tx - 80, yy, tx + 80, yy + 100, paint((60, 30, 50), 6))
    c.drawRect(skia.Rect.MakeXYWH(tx - 90, GROUND - 760, 180, 130), paint((90, 50, 60), fill=True))
    c.drawRect(skia.Rect.MakeXYWH(tx - 70, GROUND - 740, 140, 60), paint((255, 200, 110), fill=True))
    roof = skia.Path()
    roof.moveTo(tx - 120, GROUND - 760)
    roof.lineTo(tx, GROUND - 840)
    roof.lineTo(tx + 120, GROUND - 760)
    roof.close()
    c.drawPath(roof, paint((60, 30, 50), fill=True))
    rnd = random.Random(12)
    for i in range(16):
        x = rnd.uniform(-150, W + 150) - cam * 0.6
        h = rnd.uniform(260, 460)
        if abs(x - tx) < 140:
            continue
        for k in range(3):
            tri = skia.Path()
            y0 = GROUND - h + k * h * 0.25
            tri.moveTo(x, y0)
            tri.lineTo(x - 90 - k * 20, y0 + h * 0.45)
            tri.lineTo(x + 90 + k * 20, y0 + h * 0.45)
            tri.close()
            c.drawPath(tri, paint((30, 60, 70) if i % 2 else (24, 50, 62), fill=True))
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, H), paint((40, 60, 60), fill=True))
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, 50), paint((55, 80, 70), fill=True))


@setting("stadium")
def _stadium(c, t, cam):
    """Old stadium: crowd stands and a running track."""
    _grad(c, (255, 120, 150), (255, 200, 140), 0, 700)
    rnd = random.Random(14)
    for row in range(9):
        y = 640 + row * 70
        c.drawRect(skia.Rect.MakeXYWH(-400, y, W + 800, 70), paint((90 + row * 6, 50, 110), fill=True))
        for i in range(30):
            x = (i * 44 + row * 17) - cam * 0.3
            bob = 6 * math.sin(t * 6 + i + row) if (i + row) % 3 == 0 else 0
            c.drawCircle(x, y + 30 + bob, 13, paint(rnd.choice([(255, 220, 200), (255, 200, 120), (240, 240, 255), DISCO[0], DISCO[1]]), fill=True))
    c.drawRect(skia.Rect.MakeXYWH(-400, 1270, W + 800, GROUND - 1270), paint((70, 110, 70), fill=True))
    c.drawRect(skia.Rect.MakeXYWH(-400, GROUND, W + 800, H), paint((190, 80, 70), fill=True))
    for yy in (GROUND + 70, GROUND + 160, GROUND + 270):
        c.drawLine(-400, yy, W + 400, yy, paint((250, 240, 240), 5))


# --------------------------------------------------------------- new props + fx
def draw_emu(c, x, t, facing=1, moving=False, scale=1.0):
    c.save()
    c.translate(x, GROUND)
    c.scale(facing * scale, scale)
    ph = t * 11 if moving else 0
    bob = 6 * math.sin(ph * 2) if moving else 3 * math.sin(t * 2)
    c.drawOval(skia.Rect.MakeXYWH(-90, -14, 180, 26), paint((0, 0, 0), fill=True, alpha=110))
    for k, off in ((0, 0), (1, math.pi)):
        sw = math.sin(ph + off) if moving else (0.15 if k else -0.15)
        hip = (0, -175 + bob)
        knee = (20 + 30 * sw, -90)
        foot = (55 * sw, 0)
        col = (150, 120, 90) if k == 0 else (120, 95, 75)
        c.drawLine(*hip, *knee, paint(col, 10))
        c.drawLine(*knee, *foot, paint(col, 9))
        c.drawLine(foot[0] - 14, 0, foot[0] + 22, 0, paint(col, 7))
    c.drawOval(skia.Rect.MakeXYWH(-95, -275 + bob, 185, 125), glow(DISCO[0], 0, 16, 130, fill=True))
    c.drawOval(skia.Rect.MakeXYWH(-95, -275 + bob, 185, 125), paint((70, 58, 66), fill=True))
    rnd = random.Random(3)
    for i in range(14):
        fx, fy = rnd.uniform(-80, 70), rnd.uniform(-260, -170)
        c.drawLine(fx, fy + bob, fx - 16, fy + 26 + bob, paint((100, 86, 92), 5))
    nb = 8 * math.sin(t * 3)
    neck = skia.Path()
    neck.moveTo(55, -240 + bob)
    neck.quadTo(95, -330 + bob, 80 + nb, -410 + bob)
    c.drawPath(neck, paint((100, 120, 170), 18))
    hx, hy = 82 + nb, -420 + bob
    c.drawCircle(hx, hy, 22, paint((80, 70, 80), fill=True))
    c.drawLine(hx + 18, hy + 2, hx + 50, hy + 8, paint((60, 50, 50), 7))
    c.drawCircle(hx + 6, hy - 5, 7, paint((255, 255, 255), fill=True))
    c.drawCircle(hx + 8, hy - 5, 3.5, paint((20, 20, 28), fill=True))
    c.restore()


def draw_extra_prop(c, pr, t):
    kind = pr.get("kind")
    if kind == "emu":
        draw_emu(c, pr["_x"], t + pr["_x0"] * 0.01, pr.get("facing", 1), pr.get("_moving", False), float(pr.get("scale", 1.0)))
        return True
    if kind == "flock":  # a crowd of emus across the field
        n = int(pr.get("n", 5))
        for i in range(n):
            xx = pr["_x"] + (i - n / 2) * 150 + 30 * math.sin(i * 2.3)
            draw_emu(c, xx, t + i * 0.37, pr.get("facing", 1), pr.get("_moving", False), 0.62 + 0.1 * (i % 3))
        return True
    if kind == "disco_ball":
        disco_ball(c, pr["_x"], float(pr.get("y", 470)), float(pr.get("r", 62)), t)
        return True
    if kind == "ship":
        _ship(c, pr["_x"], float(pr.get("y", GROUND - 60)), float(pr.get("scale", 0.9)))
        return True
    if kind == "eiffel":
        _eiffel(c, pr["_x"], GROUND, float(pr.get("scale", 0.9)), t)
        return True
    return False


def fx_extra(c, names, t, joints):
    if "rain" in names:
        rnd = random.Random(5)
        for i in range(140):
            x = (rnd.uniform(-200, W + 200) + t * 260) % (W + 400) - 200
            y = (rnd.uniform(0, H) + t * 1500) % (GROUND + 200)
            c.drawLine(x, y, x - 14, y + 46, paint((200, 190, 255), 3, alpha=140))
    if "confetti" in names:
        rnd = random.Random(21)
        for i in range(70):
            x = rnd.uniform(0, W) + 40 * math.sin(t * 2 + i)
            y = (rnd.uniform(-600, 0) + t * rnd.uniform(300, 520)) % (GROUND + 300)
            c.save()
            c.translate(x, y)
            c.rotate(t * 300 + i * 40)
            c.drawRect(skia.Rect.MakeXYWH(-9, -5, 18, 10), paint(DISCO[i % 4], fill=True))
            c.restore()
    if "lightning" in names:
        strike = t < 0.55
        target = None
        if joints:
            target = list(joints.values())[-1]["head"]
        if strike and target:
            rnd = random.Random(int(t * 14))
            pts = [(target[0] + rnd.uniform(-160, 160), -80)]
            n = 9
            for i in range(1, n):
                k = i / n
                pts.append((lerp(pts[0][0], target[0], k) + rnd.uniform(-70, 70), lerp(-80, target[1] - 40, k)))
            pts.append((target[0], target[1] - 40))
            path = skia.Path()
            path.moveTo(*pts[0])
            for p in pts[1:]:
                path.lineTo(*p)
            c.drawPath(path, glow((200, 170, 255), 34, 18, 255))
            c.drawPath(path, paint((255, 255, 255), 9))


def overlay_extra(c, names, t):
    if "lightning" in names:
        a = 0
        if t < 0.55:
            a = 230 * (1 - t / 0.55) * (0.6 + 0.4 * (int(t * 20) % 2))
        if a > 1:
            c.drawRect(skia.Rect.MakeXYWH(0, 0, W, H), paint((240, 230, 255), fill=True, alpha=int(a)))


def title_text(c, text, x, y, size, max_w):
    """Big scene title: pink-to-orange gradient fill with a heavy dark outline and glow."""
    from .stick import typeface, wrap_text
    font = skia.Font(typeface(), size)
    lines = wrap_text(str(text).upper(), font, max_w)
    lh = size * 1.05
    y0 = y - (len(lines) - 1) * lh / 2 + size * 0.35
    for i, ln in enumerate(lines):
        w = font.measureText(ln)
        bx, by = x - w / 2, y0 + i * lh
        c.drawString(ln, bx, by, font, glow(DISCO[0], size * 0.18, 14, 200))
        c.drawString(ln, bx, by, font, paint(INK, size * 0.16))
        fill = skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
            [(bx, by - size), (bx + w, by)], [rgb((255, 255, 255)), rgb((255, 190, 220)), rgb(DISCO[1])], [0, 0.35, 1]))
        c.drawString(ln, bx, by, font, fill)
