"""Director + renderer for the 'lit set' stickman style (see lit.py for the drawing).

Scene JSON (per scene, inside a script with "style": "lit"):
  "say": narration line (one sentence per scene)
  "place": {"kind": "exterior", "light": "golden", "ground": "#c9a45c", "ground_style": "wheat|furrows|road|cobbles",
            "items": [{"name": "farmhouse", "x": 0.3, "z": 0.6}, ...]}
        or {"kind": "interior", "light": "warm", "wall": "#8a6f5c", "floor": "planks|tiles", "carpet": "#7a2c3a",
            "ceiling_lamps": [0.3, 0.7], "items": [{"name": "desk", "x": 0.6, "z": 0.2}, ...]}
  "light_from": -1 (left) or 1 (right)
  "fg": "wheat|fence_post|plant|curtain|lamp|leaves"  (soft blurred foreground object), "fg_side": 1
  "actors": [{"id": "major", "x": 0.4, "z": 0.0, "look": {...}, "do": [...steps...], "face": "smug"}]
  "crowd": {"n": 8, "kind": "soldiers|farmers|townsfolk|officials", "z": [0.35, 0.8], "action": "cheer"}
  "props": [{"kind": "flock", "x": 0.7, "z": 0.3, "n": 6, "move_to": 0.2, "move_time": 2, "at": 0.5, "scatter": true}]
  "punch": ["guns", "jammed"]   words that get a quick camera punch-in
  "sfx": [{"on": "guns", "sound": "gunburst"}, {"at": 1.2, "sound": "crash"}]
  "key": ["1932", "emus"]      caption words drawn in yellow
"""
from __future__ import annotations

import copy
import math
import random
import tempfile
from pathlib import Path

import numpy as np
import skia
from PIL import Image

from . import lit as Lt
from .stick import BASE, MOVING, act_pose, auto_steps, blend, ease, lerp, typeface

W, H = 1080, 1920
FPS = 30
CAP_Y = int(H * 0.68)
YELLOW = (242, 194, 48)

CROWD_LOOKS = {
    "soldiers": dict(hat=["slouch"], outfit=["uniform"], colors=["#8a7a4a", "#7d7045", "#90804f"], hat_colors=["#6e6040", "#5f5338"]),
    "farmers": dict(hat=["straw", "cap", ""], outfit=["overalls", "shirt"], colors=["#3f5f8f", "#8f4f3f", "#5f7f4f", "#b08a5a"],
                    hat_colors=["#d9b46a", "#7a4f3a"]),
    "townsfolk": dict(hat=["bowler", "cap", "", ""], outfit=["jacket", "shirt", "dress", "coat"],
                      colors=["#c0504d", "#4f81bd", "#9bbb59", "#8064a2", "#f79646", "#4bacc6"], hat_colors=["#222228", "#5a3e2b"]),
    "officials": dict(hat=["bowler", "top", ""], outfit=["jacket", "waistcoat"], colors=["#2f3f5f", "#3a3a48", "#4a3f35"],
                      hat_colors=["#222228"]),
}


class Stage:
    def __init__(self):
        self.chars = {}
        self.key = None

    # ------------------------------------------------------------ scene setup
    def setup(self, sc, key, dur):
        self.key = key
        self.dur = dur
        self.light = Lt.Light(sc.get("place", {}).get("light", "golden"), int(sc.get("light_from", -1)))
        self.interior = sc.get("place", {}).get("kind") == "interior"
        far_ground = (Lt.WALL_BASE + 70) if self.interior else (Lt.HORIZON + 60)
        self.cast = []
        for i, a in enumerate(sc.get("actors", [])):
            cid = str(a.get("id", f"a{i}"))
            ch = self.chars.get(cid)
            if ch is None:
                ch = Lt.Char(cid, a)
                self.chars[cid] = ch
            else:
                ch.update(a)
            if "x" in a:
                ch.x = W * float(a["x"])
            z = float(a.get("z", 0.0))
            ch.ht = ch.ht_base * lerp(1.0, 0.42, z)
            ch.ground = lerp(Lt.FLOOR, far_ground, z)
            ch.z = z
            if "facing" in a:
                ch.facing = int(a["facing"])
            ch.face = a.get("face", "neutral")
            ch.prop = a.get("prop", "")
            ch._from = dict(ch.last_pose)
            ch._x0 = ch.x
            ch._steps = auto_steps(a, cid, dur, sc.get("speaker") == cid)
            ch._si = -1
            self.cast.append(ch)
        # crowd of extras
        cr = sc.get("crowd")
        self.crowd = []
        if cr:
            look = CROWD_LOOKS.get(cr.get("kind", "townsfolk"), CROWD_LOOKS["townsfolk"])
            rnd = random.Random(hash(str(key)) % 1000 + int(cr.get("n", 8)))
            z0, z1 = cr.get("z", [0.35, 0.8])
            n = int(cr.get("n", 8))
            for i in range(n):
                spec = {"look": {"hat": rnd.choice(look["hat"]), "outfit": rnd.choice(look["outfit"]), "color": rnd.choice(look["colors"]),
                                 "hat_color": rnd.choice(look["hat_colors"]), "hair": rnd.choice(["", "short", "long", "bun"]),
                                 "moustache": rnd.random() < 0.25, "glasses": "round" if rnd.random() < 0.15 else "",
                                 "height": rnd.uniform(0.85, 1.05)}}
                ch = Lt.Char(f"x{i}", spec)
                z = lerp(z0, z1, (i % 4) / 3 if n > 1 else 0) + rnd.uniform(-0.05, 0.05)
                ch.x = W * (0.08 + 0.84 * ((i * 0.618) % 1))
                ch.ht = ch.ht_base * lerp(1.0, 0.42, z)
                ch.ground = lerp(Lt.FLOOR, far_ground, z)
                ch.z = z
                ch.facing = rnd.choice([-1, 1])
                ch.face = cr.get("face", rnd.choice(["neutral", "happy", "shock"]))
                acts = {"cheer": ["cheer", "celebrate", "laugh"], "laugh": ["laugh", "point", "laugh"], "look": ["look", "idle", "nod"],
                        "shock": ["shocked", "look"], "work": ["explain", "think", "look"]}.get(cr.get("action", "look"), ["look", "idle"])
                ch._steps = [{"at": 0.0, "action": rnd.choice(acts)}, {"at": rnd.uniform(0.8, 1.6), "action": rnd.choice(acts)},
                             {"at": rnd.uniform(2.0, 3.0), "action": rnd.choice(acts)}]
                ch._si = -1
                ch._from = dict(BASE)
                ch._x0 = ch.x
                self.crowd.append(ch)
        for pr in sc.get("props", []):
            pr["_x0"] = W * float(pr.get("x", 0.5))
            pr["_x"] = pr["_x0"]

    # ------------------------------------------------------------ animation
    def _animate(self, ch, lt, talking_id):
        steps = ch._steps
        si = max([k for k, st in enumerate(steps) if float(st.get("at", 0)) <= lt] or [0])
        st = steps[si]
        if si != ch._si:
            ch._si = si
            ch._x0 = ch.x
            ch._from = dict(ch.last_pose)
            if st.get("face"):
                ch.face = st["face"]
            if "facing" in st:
                ch.facing = int(st["facing"])
            if "prop" in st:
                ch.prop = st["prop"]
        slt = max(0.0, lt - float(st.get("at", 0)))
        action = st.get("action", "idle")
        tp = slt
        if "to" in st and action in MOVING:
            x1 = W * float(st["to"])
            leg = ch.ht * 0.45
            speed = {"walk": 0.95, "run": 2.3, "sneak": 0.55}[action] * leg * float(st.get("speed", 1))
            dist_total = abs(x1 - ch._x0)
            dist = min(dist_total, slt * speed)
            ch.x = ch._x0 + math.copysign(dist, x1 - ch._x0)
            if dist_total > 3:
                ch.facing = 1 if x1 > ch._x0 else -1
            # feet stay planted: phase comes from distance travelled, not time (no moonwalking)
            stride = {"walk": 0.94, "run": 1.49, "sneak": 0.6}[action] * leg
            freq = {"walk": 7.5, "run": 12, "sneak": 5}[action]
            tp = math.pi * dist / max(1, stride) / freq
            if dist >= dist_total - 1:
                action = st.get("then", "idle")
                tp = slt
        target = act_pose(action, tp * (1 if action in MOVING else 1.0), ch)
        k = ease(slt / 0.22)
        p = blend(ch._from, target, k) if k < 1 else target
        # small overshoot when a move lands
        if 0.22 < slt < 0.45 and action not in MOVING:
            o = math.sin((slt - 0.22) / 0.23 * math.pi) * 0.08
            p = {kk: v + (v - ch._from.get(kk, v)) * o for kk, v in p.items()}
        ch.last_pose = p
        return p

    # ------------------------------------------------------------ camera
    def camera(self, sc, lt, words):
        dur = self.dur
        focus_x = 540
        movers = [c for c in self.cast if any("to" in s for s in c._steps)]
        tgt = None
        spk = sc.get("speaker")
        if movers:
            tgt = movers[0].x
        elif spk in self.chars:
            tgt = self.chars[spk].x
        if tgt is not None:
            focus_x = lerp(540, tgt, 0.35)
        z = 1.0 + 0.07 * ease(lt / max(dur, 0.1))          # slow push-in, never still
        drift = 18 * math.sin(lt * 0.7)
        punch = 0.0
        for w in words:
            if any(w["w"].lower().strip(".,!?").startswith(p.lower()) for p in sc.get("punch", [])):
                d = lt - w["lstart"]
                if 0 <= d < 0.6:
                    punch = max(punch, 0.1 * math.exp(-d * 6) * min(1, d / 0.06))
        z += punch
        fy = 960 - 120 * punch / 0.1 * 0.6
        return z, focus_x + drift, fy

    # ------------------------------------------------------------ frame
    def frame(self, sc, lt, dur, key, words):
        if key != self.key:
            self.setup(sc, key, dur)
        lt_ = self.light
        surface = skia.Surface(W, H)
        c = surface.getCanvas()
        z, fx, fy = self.camera(sc, lt, words)
        c.save()
        c.translate(W / 2, H / 2)
        c.scale(z, z)
        c.translate(-fx, -fy)
        vp = Lt.draw_set(c, sc.get("place", {}), lt_, lt, 0)
        # props behind characters (further first)
        props = sorted(sc.get("props", []), key=lambda p: -float(p.get("z", 0)))
        for pr in props:
            plt = lt - float(pr.get("at", 0))
            if plt < 0 and not pr.get("visible_before"):
                continue
            if "move_to" in pr:
                k = ease(max(0, plt) / max(0.1, float(pr.get("move_time", dur))))
                pr["_x"] = lerp(pr["_x0"], W * float(pr["move_to"]), k)
                pr["_moving"] = 0 < k < 1
                if pr["_x0"] != W * float(pr["move_to"]):
                    pr["facing"] = 1 if pr["move_to"] >= pr.get("x", 0.5) else -1
            if pr.get("scatter"):
                pr["_k"] = ease(max(0, plt) / max(0.1, float(pr.get("move_time", 1.5))))
            if float(pr.get("z", 0)) > 0.2:
                Lt.world_prop(c, lt_, pr, lt, vp)
        # who is talking right now
        talking = sc.get("speaker")
        active = any(w["lstart"] <= lt <= w["lend"] + 0.05 for w in words)
        everyone = sorted(self.crowd + self.cast, key=lambda ch: -ch.z)
        for ch in everyone:
            p = self._animate(ch, lt, talking)
            look = 0
            if talking and talking in self.chars and talking != ch.id:
                look = 1 if self.chars[talking].x > ch.x else -1
            Lt.draw_char(c, ch, p, lt, lt_, talking=(ch.id == talking and active and sc.get("talk", False)), look=look)
        for pr in props:
            if float(pr.get("z", 0)) <= 0.2 and (lt >= float(pr.get("at", 0)) or pr.get("visible_before")):
                Lt.world_prop(c, lt_, pr, lt, vp)
        c.restore()
        Lt.foreground(c, sc.get("fg"), lt_, lt, int(sc.get("fg_side", 1)))
        Lt.finish(c, lt_, lt)
        return surface


# --------------------------------------------------------------- captions (1-2 words, big, popping)
def caption_groups(words):
    out, cur = [], []
    for w in words:
        cur.append(w)
        long_word = len(w["w"]) > 7
        end = w["w"].rstrip()[-1:] in ",.!?;:"
        if len(cur) == 2 or long_word or end:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def draw_caption(c, groups, t, keys):
    g = next((g for g in groups if g[0]["start"] - 0.02 <= t < (g[-1]["end"] + 0.25)), None)
    if not g:
        return
    font = skia.Font(typeface(), 124)
    words = [w["w"].upper().strip() for w in g]
    widths = [font.measureText(w) for w in words]
    total = sum(widths) + 34 * (len(words) - 1)
    x = W / 2 - total / 2
    # soft dark blurred shadow
    sh = skia.Paint(AntiAlias=True, Color=skia.Color(10, 8, 16, 150))
    sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 30))
    c.drawRoundRect(skia.Rect.MakeXYWH(x - 50, CAP_Y - 110, total + 100, 170), 60, 60, sh)
    for w, wd, src in zip(words, widths, g):
        d = t - src["start"]
        s = 1.0 if d < 0 else (0.6 + 0.4 * min(1, d / 0.09) + 0.12 * math.sin(min(1, d / 0.18) * math.pi))
        on = d >= 0
        bare = w.strip(".,!?;:\"'").lower()
        key = bare in keys or any(ch.isdigit() for ch in bare)
        c.save()
        c.translate(x + wd / 2, CAP_Y)
        c.scale(s, s)
        st = skia.Paint(AntiAlias=True, Color=skia.Color(15, 15, 18, 255 if on else 120), Style=skia.Paint.kStroke_Style, StrokeWidth=20,
                        StrokeJoin=skia.Paint.kRound_Join)
        c.drawString(w, -wd / 2, 0, font, st)
        col = YELLOW if key else (255, 255, 255)
        c.drawString(w, -wd / 2, 0, font, skia.Paint(AntiAlias=True, Color=skia.Color(*col, 255 if on else 110)))
        c.restore()
        x += wd + 34


# --------------------------------------------------------------- sound design
def synth(kind, seed=0):
    from ..audio import SR, _lowpass
    rng = np.random.default_rng(seed + 11)
    def env(L, a=0.004, dec=6.0):
        t = np.arange(L) / SR
        return np.minimum(1, t / a) * np.exp(-t * dec)
    def noise(L):
        return rng.standard_normal(L).astype(np.float32)
    def band(x, lo, hi):
        return _lowpass(x, hi) - _lowpass(x, lo)
    if kind == "gunburst":  # rapid machine-gun burst: layered cracks + low thumps
        L = int(1.1 * SR)
        y = np.zeros(L, np.float32)
        for i in range(9):
            s = int(i * 0.09 * SR)
            n = int(0.12 * SR)
            crack = band(noise(n), 300, 5000) * env(n, 0.001, 38)
            t = np.arange(n) / SR
            thump = np.sin(2 * np.pi * (90 - 40 * t / t[-1]) * t) * env(n, 0.002, 25)
            y[s:s + n] += 0.6 * crack + 0.5 * thump
        return 0.6 * y / (np.abs(y).max() + 1e-6)
    if kind == "clank":  # gun jamming: metallic clank + click
        L = int(0.6 * SR)
        t = np.arange(L) / SR
        y = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, d in ((420, 14), (1130, 22), (2650, 30)))
        y += 0.5 * band(noise(L), 1500, 7000) * env(L, 0.001, 60)
        return (0.45 * y / np.abs(y).max()).astype(np.float32)
    if kind == "rumble":  # stampede of feet
        L = int(1.6 * SR)
        y = np.zeros(L, np.float32)
        for i in range(30):
            s = int(rng.uniform(0, 1.4) * SR)
            n = int(0.08 * SR)
            y[s:s + n] += _lowpass(noise(n), 300) * env(n, 0.002, 30)
        y += 0.3 * _lowpass(noise(L), 120)
        y *= np.sin(np.linspace(0, np.pi, L)) ** 0.5
        return 0.7 * y / (np.abs(y).max() + 1e-6)
    if kind in ("crunch", "crash"):  # wood breaking / crops trampled
        L = int((0.5 if kind == "crunch" else 0.9) * SR)
        y = np.zeros(L, np.float32)
        for i in range(14 if kind == "crash" else 8):
            s = int(rng.uniform(0, 0.35 if kind == "crunch" else 0.5) * SR)
            n = int(0.06 * SR)
            y[s:s + n] += band(noise(n), 400, 4000) * env(n, 0.001, 50)
        t = np.arange(L) / SR
        y += (0.5 if kind == "crash" else 0.2) * np.sin(2 * np.pi * 70 * t) * np.exp(-t * 8)
        return 0.6 * y / (np.abs(y).max() + 1e-6)
    if kind == "paper":
        L = int(0.5 * SR)
        y = band(noise(L), 1500, 8000) * (0.4 + 0.6 * np.abs(np.sin(np.linspace(0, 9, L)))) * env(L, 0.01, 4)
        return (0.3 * y / np.abs(y).max()).astype(np.float32)
    if kind == "typewriter":
        L = int(0.9 * SR)
        y = np.zeros(L, np.float32)
        for i in range(8):
            s = int(i * 0.09 * SR + rng.uniform(0, 0.02) * SR)
            n = int(0.03 * SR)
            y[s:s + n] += band(noise(n), 2000, 7000) * env(n, 0.0005, 120)
        t = np.arange(L) / SR
        y += 0.4 * np.sin(2 * np.pi * 2100 * t) * np.exp(-(t - 0.8).clip(0) * 9) * (t > 0.8)
        return 0.45 * y / (np.abs(y).max() + 1e-6)
    if kind == "engine":
        L = int(1.6 * SR)
        t = np.arange(L) / SR
        f = 45 + 15 * np.minimum(1, t / 0.8)
        y = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * 0.5 + 0.4 * _lowpass(noise(L), 400)
        y = _lowpass(y, 900) * np.minimum(1, t / 0.15) * np.minimum(1, (t[-1] - t) / 0.4)
        return (0.35 * y / np.abs(y).max()).astype(np.float32)
    if kind == "splash":
        L = int(0.8 * SR)
        y = band(noise(L), 500, 6000) * env(L, 0.005, 5)
        t = np.arange(L) / SR
        y += 0.3 * np.sin(2 * np.pi * (300 - 200 * t) * t) * np.exp(-t * 6)
        return (0.4 * y / np.abs(y).max()).astype(np.float32)
    if kind == "drum":  # emu's low booming call
        L = int(0.9 * SR)
        t = np.arange(L) / SR
        y = np.zeros(L)
        for i in range(4):
            s = i * 0.18
            y += np.sin(2 * np.pi * 70 * (t - s)) * np.exp(-((t - s).clip(0)) * 14) * (t > s)
        return (0.55 * y / np.abs(y).max()).astype(np.float32)
    if kind == "laugh":  # crowd laughter: chopped vocal-ish noise bursts
        L = int(1.4 * SR)
        y = np.zeros(L, np.float32)
        for v in range(6):
            f0 = rng.uniform(160, 320)
            for i in range(6):
                s = int((v * 0.05 + i * 0.17) * SR)
                n = int(0.12 * SR)
                if s + n > L:
                    continue
                t = np.arange(n) / SR
                y[s:s + n] += (np.sin(2 * np.pi * f0 * t) * 0.5 + 0.5 * band(noise(n), 300, 2500)) * np.sin(np.linspace(0, np.pi, n))
        return 0.35 * y / (np.abs(y).max() + 1e-6)
    if kind == "cash":
        L = int(0.9 * SR)
        t = np.arange(L) / SR
        y = 0.5 * band(noise(L), 2000, 8000) * env(L, 0.001, 40)
        y += (np.sin(2 * np.pi * 2637 * t) + 0.6 * np.sin(2 * np.pi * 3520 * t)) * np.exp(-((t - 0.12).clip(0)) * 5) * (t > 0.12)
        return (0.3 * y / np.abs(y).max()).astype(np.float32)
    if kind == "thud":
        L = int(0.5 * SR)
        t = np.arange(L) / SR
        y = np.sin(2 * np.pi * (110 - 60 * t / t[-1]) * t) * np.exp(-t * 12) + 0.3 * _lowpass(noise(L), 500) * np.exp(-t * 20)
        return (0.6 * y / np.abs(y).max()).astype(np.float32)
    if kind == "whistle":  # train / referee
        L = int(0.9 * SR)
        t = np.arange(L) / SR
        y = (np.sin(2 * np.pi * 880 * t) + 0.5 * np.sin(2 * np.pi * 1320 * t)) * np.minimum(1, t / 0.05) * np.minimum(1, (t[-1] - t) / 0.2)
        y += 0.2 * band(noise(L), 1000, 4000)
        return (0.25 * y / np.abs(y).max()).astype(np.float32)
    if kind == "wind":
        L = int(2.0 * SR)
        y = _lowpass(noise(L), 600) * (0.5 + 0.5 * np.sin(np.linspace(0, 6, L)))
        y *= np.sin(np.linspace(0, np.pi, L))
        return (0.3 * y / np.abs(y).max()).astype(np.float32)
    if kind == "bell":
        L = int(1.4 * SR)
        t = np.arange(L) / SR
        y = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, a, d in ((660, 1, 2.5), (1320, 0.5, 3.5), (1980, 0.3, 5)))
        return (0.3 * y / np.abs(y).max()).astype(np.float32)
    return None


def render_lit(script, out_path, cfg, seed=0):
    from .. import audio as A
    from . import disco as D
    from .core import Encoder
    from .scenes import build_timeline
    A.configure(cfg)
    timeline, vev, sev, total = build_timeline(script, None, None)
    sev = []  # this style places its own sound effects on words
    for i, seg in enumerate(timeline):
        sc = seg["scene"]
        for w in seg["words"]:
            w["lstart"] = w["start"] - seg["start"]
            w["lend"] = w["end"] - seg["start"]
        if i:
            sev.append((seg["start"] - 0.12, "whoosh"))
        for cue in sc.get("sfx", []):
            if "at" in cue:
                sev.append((seg["start"] + float(cue["at"]), cue["sound"]))
            elif cue.get("on"):
                w = next((w for w in seg["words"] if w["w"].lower().strip(".,!?;:'\"").startswith(cue["on"].lower())), None)
                if w:
                    sev.append((w["start"] + float(cue.get("offset", 0)), cue["sound"]))
    words = [w for seg in timeline for w in seg["words"]]
    groups = caption_groups(words)
    keys = {k.lower() for seg in timeline for k in seg["scene"].get("key", [])}
    mixed = A.mix(total, vev, sev, music_seed=seed, music_gain=cfg.get("music_gain", 0.32) * 0.8)
    tmp = Path(tempfile.mkdtemp())
    wav = str(tmp / "mix.wav")
    A.write_wav(wav, mixed)
    stage = Stage()
    nxt = Stage()
    enc = Encoder(out_path, wav)
    WHIP = 0.24
    for fi in range(int(total * FPS)):
        t = fi / FPS
        si = next((i for i, s in enumerate(timeline) if s["start"] <= t < s["end"]), len(timeline) - 1)
        seg = timeline[si]
        lt, d = t - seg["start"], seg["end"] - seg["start"]
        surf = stage.frame(seg["scene"], lt, d, si, seg["words"])
        out = skia.Surface(W, H)
        oc = out.getCanvas()
        if lt > d - WHIP and si + 1 < len(timeline):  # whip-slide into the next scene
            u = ease((lt - (d - WHIP)) / WHIP)
            nseg = timeline[si + 1]
            nxt.chars = copy.deepcopy(stage.chars)  # preview the next scene without disturbing this one
            nxt.key = None
            ns = nxt.frame(nseg["scene"], 0.0, nseg["end"] - nseg["start"], si + 1, nseg["words"])
            bl = 40 * math.sin(u * math.pi)
            pnt = skia.Paint(ImageFilter=skia.ImageFilters.Blur(bl + 0.01, 1.0))
            oc.drawImage(surf.makeImageSnapshot(), -u * W, 0, paint=pnt)
            oc.drawImage(ns.makeImageSnapshot(), (1 - u) * W, 0, paint=pnt)
            nxt.key = None
        else:
            oc.drawImage(surf.makeImageSnapshot(), 0, 0)
        draw_caption(oc, groups, t, keys)
        arr = out.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType)[:, :, :3]
        img = Image.fromarray(np.ascontiguousarray(arr))
        D.progress_segments(img, len(timeline), si, lt / d)
        enc.write(img)
    enc.close()
    return {"duration": total, "path": out_path}
