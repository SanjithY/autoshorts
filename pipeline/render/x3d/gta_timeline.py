"""'13 years in 40 seconds': a vinyl-toy tourist walks a neon road through GTA 6's timeline (runs inside bpy).

Our own character and set only: no Rockstar logos, characters or artwork. The road runs along +X on the studio
floor; milestones stand behind it (+Y) so the camera (at -Y) sees the walker in front of them.

State tracks:
  x        walker position along the road (feet)          walk    0..1 gait amount (legs/arms swing)
  face     0 = faces +X (walking), 1 = faces the camera   beard   0..1 beard length (the years pass...)
  cheer    0..1 arms up + hop                             tv      0..1 the 2023 TV switches on, view counter pops up
  stamp1/2 0..1 "DELAYED" stamps slam onto the calendars  cash    0..1 money stacks rise at the finish
  confetti 0..1 switches confetti on (falls with time)    arch    0..1 finish arch lights up
Anchors: "hero" (walker's chest), "head".
"""
from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

FLOOR = -2.0
X0 = {"2013": -13.0, "2022": -7.5, "2023": -2.0, "cal": 3.6, "end": 10.5}
STRIDE = 0.78


def _mat(name, col, rough=0.3, metal=0.0, emit=None, strength=0.0, coat=0.6):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    for key in ("Coat Weight", "Clearcoat"):
        if key in b.inputs:
            b.inputs[key].default_value = coat
            break
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def _shirt_mat():
    """Loud tourist shirt: hot pink with teal + orange blossoms (procedural, so it's our own pattern)."""
    m = bpy.data.materials.new("shirt")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.45
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 9.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (1.0, 0.55, 0.1, 1)
    els[1].position, els[1].color = 0.13, (0.05, 0.75, 0.7, 1)
    e3 = els.new(0.24)
    e3.color = (0.95, 0.12, 0.45, 1)
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    nt.links.new(vor.outputs["Distance"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def _add(kind, mat=None, parent=None, smooth=True, **kw):
    getattr(bpy.ops.mesh, f"primitive_{kind}_add")(**kw)
    o = bpy.context.object
    if smooth:
        bpy.ops.object.shade_smooth()
    if mat:
        o.data.materials.append(mat)
    if parent:
        o.parent = parent
    return o


def _empty(name, loc=(0, 0, 0), parent=None):
    o = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    if parent:
        o.parent = parent
    return o


def _text(body, size, mat, loc, extrude=0.06, align="CENTER", parent=None):
    bpy.ops.object.text_add(location=loc)
    t = bpy.context.object
    t.data.body = body
    t.data.size = size
    t.data.extrude = extrude
    t.data.bevel_depth = 0.012
    t.data.align_x = align
    t.data.align_y = "CENTER"
    t.rotation_euler = (math.pi / 2, 0, 0)   # stand up, facing -Y (the camera)
    t.data.materials.append(mat)
    if parent:
        t.parent = parent
    return t


class Model:
    def __init__(self):
        rnd = random.Random(13)
        self.M = M = {
            "skin": _mat("skin", (0.93, 0.66, 0.48), 0.35),
            "shirt": _shirt_mat(),
            "shorts": _mat("shorts", (0.12, 0.35, 0.85), 0.4),
            "white": _mat("white", (0.95, 0.95, 0.97), 0.25),
            "black": _mat("black", (0.02, 0.02, 0.03), 0.08, 0.3),
            "hat": _mat("hat", (0.98, 0.92, 0.75), 0.5, coat=0.2),
            "band": _mat("band", (0.05, 0.7, 0.65), 0.4),
            "beard": _mat("beard", (0.55, 0.52, 0.5), 0.7, coat=0.0),
            "road": _mat("road", (0.07, 0.06, 0.09), 0.25, coat=0.3),
            "lane": _mat("lane", (1, 0.85, 0.3), 0.4, emit=(1, 0.75, 0.2), strength=4),
            "neon_pink": _mat("neonp", (1, 0.3, 0.6), 0.4, emit=(1, 0.2, 0.55), strength=14),
            "neon_teal": _mat("neont", (0.2, 1, 0.9), 0.4, emit=(0.1, 0.95, 0.85), strength=12),
            "neon_orange": _mat("neono", (1, 0.6, 0.2), 0.4, emit=(1, 0.5, 0.1), strength=12),
            "plinth": _mat("plinth", (0.1, 0.06, 0.14), 0.2),
            "cone": _mat("cone", (1, 0.38, 0.05), 0.35),
            "case": _mat("case", (0.1, 0.25, 0.75), 0.25),
            "screen_off": _mat("screen", (0.02, 0.02, 0.04), 0.1),
            "red": _mat("red", (0.85, 0.05, 0.08), 0.35),
            "stamp": _mat("stamp", (0.9, 0.04, 0.08), 0.5, emit=(0.9, 0.0, 0.05), strength=2),
            "cash": _mat("cash", (0.2, 0.6, 0.3), 0.55, coat=0.1),
            "band_cash": _mat("bandc", (0.95, 0.85, 0.5), 0.4),
        }
        self._build_road()
        self._build_walker()
        self._build_stations(rnd)

    # ---------- set ----------
    def _build_road(self):
        M = self.M
        _add("cube", M["road"], smooth=False, size=1, location=(-3.0, 0, FLOOR + 0.01)).scale = (35, 2.4, 0.04)
        for k in range(43):
            d = _add("cube", M["lane"], smooth=False, size=1, location=(-19.0 + k * 0.8, 0, FLOOR + 0.035))
            d.scale = (0.38, 0.06, 0.01)
        for y in (-1.25, 1.25):
            e = _add("cube", M["neon_pink"], smooth=False, size=1, location=(-1.5, y, FLOOR + 0.04))
            e.scale = (32, 0.03, 0.03)
        # soft lights along the road so every station is lit like the studio centre
        for x in (-13, -7.5, -2, 3.6, 10.5):
            bpy.ops.object.light_add(type="AREA", location=(x - 1.5, -3.5, FLOOR + 4.5))
            l = bpy.context.object
            l.data.energy, l.data.size, l.data.color = 900, 4, (1.0, 0.85, 0.75)
            l.rotation_euler = (Vector((x, 0.5, FLOOR + 0.8)) - l.location).to_track_quat("-Z", "Y").to_euler()
            bpy.ops.object.light_add(type="AREA", location=(x + 2.0, 2.5, FLOOR + 2.5))
            r = bpy.context.object
            r.data.energy, r.data.size, r.data.color = 500, 3, (1.0, 0.3, 0.65)
            r.rotation_euler = (Vector((x, 0, FLOOR + 1.0)) - r.location).to_track_quat("-Z", "Y").to_euler()

    def _year(self, x, label, mat):
        p = _add("cube", self.M["plinth"], smooth=False, size=1, location=(x, 2.4, FLOOR + 0.15))
        p.scale = (2.4, 0.9, 0.3)
        _text(label, 1.05, mat, (x, 2.3, FLOOR + 0.95), extrude=0.08)

    def _build_stations(self, rnd):
        M = self.M
        # 2013: a big blank game case with a glowing "V"
        x = X0["2013"]
        self._year(x, "2013", M["neon_pink"])
        case = _add("cube", M["case"], smooth=False, size=1, location=(x + 1.9, 1.5, FLOOR + 0.75))
        case.scale = (0.85, 0.12, 1.2)
        case.rotation_euler = (0, 0, math.radians(-12))
        _text("V", 0.7, M["neon_orange"], (x + 1.9, 1.42, FLOOR + 0.78), extrude=0.03)
        # 2022: construction zone + an "IN DEVELOPMENT" board
        x = X0["2022"]
        self._year(x, "2022", M["neon_teal"])
        for k, dx in enumerate((1.4, 1.9, 2.4)):
            c = _add("cone", M["cone"], radius1=0.18, radius2=0.03, depth=0.55, location=(x + dx, 1.3 + 0.15 * (k % 2), FLOOR + 0.29))
            _add("torus", M["white"], major_radius=0.105, minor_radius=0.03, location=(x + dx, 1.3 + 0.15 * (k % 2), FLOOR + 0.33))
        board = _add("cube", M["white"], smooth=False, size=1, location=(x - 1.9, 1.6, FLOOR + 0.9))
        board.scale = (1.5, 0.06, 0.55)
        _text("IN\nDEVELOPMENT", 0.19, M["black"], (x - 1.9, 1.55, FLOOR + 0.9), extrude=0.01)
        for dx in (-0.55, 0.55):
            _add("cylinder", M["black"], radius=0.03, depth=0.65, location=(x - 1.9 + dx, 1.62, FLOOR + 0.33))
        # 2023: a big TV that switches on, with a pop-up view counter
        x = X0["2023"]
        self._year(x, "2023", M["neon_orange"])
        tvx = x + 2.1
        frame = _add("cube", M["black"], smooth=False, size=1, location=(tvx, 1.45, FLOOR + 1.15))
        frame.scale = (1.7, 0.12, 1.0)
        for dx in (-0.6, 0.6):
            _add("cylinder", M["black"], radius=0.04, depth=0.7, location=(tvx + dx, 1.45, FLOOR + 0.33))
        self.screen_mat = _mat("screen_on", (0.02, 0.02, 0.04), 0.1, emit=(0.95, 0.35, 0.75), strength=0.0)
        scr = _add("cube", self.screen_mat, smooth=False, size=1, location=(tvx, 1.38, FLOOR + 1.15))
        scr.scale = (1.55, 0.02, 0.86)
        self.play = _add("cone", M["white"], smooth=False, vertices=3, radius1=0.22, radius2=0, depth=0.03,
                         location=(tvx + 0.03, 1.355, FLOOR + 1.15), rotation=(math.pi / 2, 0, math.pi / 2))
        self.counter = _text("90M VIEWS\nIN 24 HOURS", 0.24, M["neon_teal"], (tvx, 1.2, FLOOR + 2.05), extrude=0.03)
        # 2025 -> May 2026 -> Nov 19, 2026: three calendar pages, two get stamped DELAYED
        x = X0["cal"]
        self.stamps = []
        for k, (lab, top) in enumerate((("2025", "PROMISED"), ("MAY 26\n2026", "NEW DATE"), ("NOV 19\n2026", "FINAL DATE"))):
            cx = x + k * 1.45
            page = _add("cube", M["white"], smooth=False, size=1, location=(cx, 1.6, FLOOR + 0.85))
            page.scale = (1.2, 0.1, 1.3)
            hdr = _add("cube", M["red"], smooth=False, size=1, location=(cx, 1.54, FLOOR + 1.36))
            hdr.scale = (1.21, 0.02, 0.28)
            _text(top, 0.13, M["white"], (cx, 1.52, FLOOR + 1.36), extrude=0.005)
            _text(lab, 0.26 if "\n" in lab else 0.36, M["black"], (cx, 1.54, FLOOR + 0.76), extrude=0.01)
            for dx in (-0.4, 0.4):
                _add("torus", M["black"], major_radius=0.06, minor_radius=0.015, location=(cx + dx, 1.6, FLOOR + 1.52),
                     rotation=(0, math.pi / 2, 0))
            if k < 2:
                st = _empty(f"stamp{k}", (cx, 1.5, FLOOR + 0.8))
                plate = _add("cube", M["stamp"], smooth=False, size=1, location=(0, 0, 0), parent=st)
                plate.scale = (1.25, 0.02, 0.32)
                _text("DELAYED", 0.22, M["white"], (0, -0.02, 0), extrude=0.005, parent=st)
                st.rotation_euler = (0, math.radians(-14 if k == 0 else 11), 0)
                self.stamps.append(st)
        # finish: neon arch, money stacks, confetti
        x = X0["end"]
        bpy.ops.mesh.primitive_torus_add(major_radius=1.9, minor_radius=0.07, location=(x, 0.6, FLOOR), rotation=(math.pi / 2, 0, 0),
                                         major_segments=96)
        self.arch = bpy.context.object
        self.arch_mat = _mat("arch", (1, 0.3, 0.6), 0.4, emit=(1, 0.2, 0.55), strength=0.5)
        self.arch.data.materials.append(self.arch_mat)
        self.finish_text = _text("NOV 19, 2026", 0.42, M["neon_teal"], (x, 0.62, FLOOR + 2.35), extrude=0.05)
        self.stacks = []
        for i in range(5):
            for j in range(2):
                sx, sy = x + 1.6 + i * 0.42, 1.5 + j * 0.7
                root = _empty(f"stack{i}{j}", (sx, sy, FLOOR))
                body = _add("cube", M["cash"], smooth=False, size=1, location=(0, 0, 0.5), parent=root)
                body.scale = (0.36, 0.18, 1.0)
                b2 = _add("cube", M["band_cash"], smooth=False, size=1, location=(0, 0, 0.5), parent=root)
                b2.scale = (0.37, 0.19, 0.08)
                root["h"] = rnd.uniform(1.2, 2.6) * (1.25 if i in (2, 3) else 1.0)
                root["delay"] = (i * 2 + j) * 0.05
                root.scale = (1, 1, 0.001)
                self.stacks.append(root)
        self.confetti = []
        cols = [M["neon_pink"], M["neon_teal"], M["neon_orange"], M["white"]]
        for k in range(140):
            c = _add("plane", rnd.choice(cols), smooth=False, size=0.07, location=(x, 0, FLOOR - 5))
            c["x"], c["y"] = x + rnd.uniform(-2.6, 3.4), rnd.uniform(-1.4, 1.8)
            c["z0"], c["v"] = rnd.uniform(3.0, 5.0), rnd.uniform(0.7, 1.3)
            c["s"], c["w"] = rnd.uniform(0, 6.28), rnd.uniform(3, 7)
            c.visible_shadow = False
            self.confetti.append(c)

    # ---------- the walker (vinyl-toy tourist) ----------
    def _build_walker(self):
        M = self.M
        self.root = _empty("walker", (-16.0, -0.1, FLOOR))
        self.body = _empty("body", (0, 0, 0), self.root)
        self.legs, self.arms = [], []
        for side in (-1, 1):
            hip = _empty("hip", (0, 0.12 * side, 0.52), self.body)
            leg = _add("cylinder", M["skin"], parent=hip, radius=0.075, depth=0.4, location=(0, 0, -0.24))
            shoe = _add("uv_sphere", M["white"], parent=hip, radius=0.12, location=(0.05, 0, -0.46))
            shoe.scale = (1.35, 0.85, 0.55)
            self.legs.append(hip)
        shorts = _add("cylinder", M["shorts"], parent=self.body, radius=0.25, depth=0.24, location=(0, 0, 0.6))
        torso = _add("uv_sphere", self.M["shirt"], parent=self.body, radius=0.3, location=(0, 0, 0.9))
        torso.scale = (0.9, 1.0, 1.15)
        for side in (-1, 1):
            sh = _empty("shoulder", (0, 0.31 * side, 1.08), self.body)
            sleeve = _add("uv_sphere", M["shirt"], parent=sh, radius=0.1, location=(0, 0.02 * side, -0.05))
            arm = _add("cylinder", M["skin"], parent=sh, radius=0.06, depth=0.34, location=(0, 0.02 * side, -0.22))
            hand = _add("uv_sphere", M["skin"], parent=sh, radius=0.075, location=(0, 0.02 * side, -0.41))
            self.arms.append(sh)
        self.head = _empty("head", (0, 0, 1.47), self.body)
        _add("uv_sphere", M["skin"], parent=self.head, radius=0.33, location=(0, 0, 0), segments=48, ring_count=24)
        for side in (-1, 1):   # sunglasses
            lens = _add("cylinder", M["black"], parent=self.head, radius=0.1, depth=0.04, location=(0.3, 0.12 * side, 0.04),
                        rotation=(0, math.pi / 2, 0))
            lens.scale = (1, 1.15, 1)
        _add("cylinder", M["black"], parent=self.head, radius=0.015, depth=0.1, location=(0.33, 0, 0.06), rotation=(math.pi / 2, 0, 0))
        smile = _add("torus", M["black"], parent=self.head, major_radius=0.07, minor_radius=0.012, location=(0.3, 0, -0.14),
                     rotation=(0, math.pi / 2, 0))
        smile.scale = (1, 1, 0.55)
        _add("uv_sphere", M["skin"], parent=self.head, radius=0.05, location=(0.33, 0, -0.03))   # nose
        brim = _add("cylinder", M["hat"], parent=self.head, radius=0.42, depth=0.03, location=(0, 0, 0.22))
        crown = _add("cylinder", M["hat"], parent=self.head, radius=0.27, depth=0.2, location=(0, 0, 0.32))
        _add("cylinder", M["band"], parent=self.head, radius=0.275, depth=0.06, location=(0, 0, 0.26))
        self.beard = _empty("beardroot", (0.2, 0, -0.16), self.head)
        b = _add("uv_sphere", M["beard"], parent=self.beard, radius=0.18, location=(0, 0, -0.12))
        b.scale = (0.7, 1.15, 1.0)
        self.beard.scale = (0.001, 0.001, 0.001)

    # ---------- per frame ----------
    def apply(self, st):
        t = float(st.get("_t", 0))
        x = float(st.get("x", X0["2013"] - 1.5))
        walk = float(st.get("walk", 0))
        face = float(st.get("face", 0))
        cheer = float(st.get("cheer", 0))
        ph = x / STRIDE * math.pi
        hop = cheer * abs(math.sin(t * 7.0)) * 0.22
        self.root.location = (x, -0.1, FLOOR + hop + walk * abs(math.sin(ph)) * 0.035)
        self.root.rotation_euler = (0, 0, -math.pi / 2 * face)
        sw = math.radians(32) * walk
        for k, hip in enumerate(self.legs):
            hip.rotation_euler = (0, math.sin(ph + k * math.pi) * sw, 0)
        for k, sh in enumerate(self.arms):
            side = -1 if k == 0 else 1
            up = math.radians(150) * cheer + math.radians(10) * math.sin(t * 9 + k * 2) * cheer
            sh.rotation_euler = (side * (math.radians(6) + up), -math.sin(ph + k * math.pi) * sw * 0.8, 0)
        self.body.rotation_euler = (0, math.radians(4) * walk, 0)
        self.head.rotation_euler = (0, 0, math.radians(6) * math.sin(t * 1.3) * (1 - walk))
        bd = float(st.get("beard", 0))
        self.beard.scale = (max(0.001, min(1, bd * 3)),) * 2 + (max(0.001, bd * 2.6),)
        # TV + counter
        tv = float(st.get("tv", 0))
        self._set_emit(self.screen_mat, 6.0 * tv)
        self.play.scale = (tv,) * 3 if tv > 0.01 else (0.001,) * 3
        k = max(0.001, min(1, (tv - 0.4) / 0.6))
        self.counter.scale = (k, k, k)
        # stamps slam down from above
        for i, s in enumerate(self.stamps):
            v = float(st.get(f"stamp{i + 1}", 0))
            s.location.z = FLOOR + 0.8 + (1 - v) ** 2 * 4.0
            s.location.y = 1.5 - (1 - v) * 0.8
        # finish
        a = float(st.get("arch", 0))
        self._set_emit(self.arch_mat, 0.5 + 18 * a)
        cash = float(st.get("cash", 0))
        for s in self.stacks:
            u = max(0.0, min(1.0, (cash - s["delay"]) / 0.55))
            s.scale = (1, 1, max(0.001, s["h"] * (1 - (1 - u) ** 3)))
        on = float(st.get("confetti", 0))
        for c in self.confetti:
            if on < 0.01:
                c.location = (c["x"], c["y"], FLOOR - 5)
                continue
            age = (on * 6.0) * c["v"]   # "confetti" ramps 0->1 over its window, so age grows with time
            z = FLOOR + c["z0"] - age * 0.9
            if z < FLOOR + 0.02:
                z = FLOOR + 0.02
            c.location = (c["x"] + 0.15 * math.sin(age * 2 + c["s"]), c["y"], z)
            c.rotation_euler = (age * c["w"], age * c["w"] * 0.7, c["s"])

    def _set_emit(self, m, v):
        """Only touch a material when its value really changes (every change makes EEVEE rebuild the shader)."""
        inp = m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
        v = round(v, 2)
        if abs(inp.default_value - v) > 1e-3:
            inp.default_value = v

    def anchor(self, name):
        if name == "head":
            return self.root.location + Vector((0, 0, 1.5))
        return self.root.location + Vector((0, 0, 0.95))
