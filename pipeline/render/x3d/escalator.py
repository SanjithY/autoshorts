"""Escalator model for the 3D explainer (runs inside Blender / bpy).

Side cutaway along X: passengers ride up to the right. The step chain runs a closed loop: up the visible
run, down around the top drive sprocket, back down underneath (steps upside down), and around the bottom
return wheel. Every step has chain wheels at its front axle and trailer wheels behind; the trailer track is
generated from the steps' own motion, so the staircase forms and flattens exactly as in a real escalator.

State: travel (distance the chain has moved, computed from "speed"), hero (index of the pink step),
xray (0..1 fades the far side cladding), handrail (1 shows handrails).
Anchors for the camera: "hero" (tread centre of the hero step), "ride:<s>" (a point riding the loop).
"""
from __future__ import annotations

import bisect
import math

import bpy
from mathutils import Euler, Matrix, Vector

PITCH_TARGET = 0.4
TREAD_D, RISE, TREAD_TOP = 0.38, 0.2, 0.24
WIDTH = 1.0
Z0 = -0.25   # lift the whole machine so the bottom return wheel clears the studio floor


def _mat(name, col, metal=0.0, rough=0.4, emit=None, strength=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            m.blend_method = "BLEND"
    return m


def _chaikin(pts, it=4):
    for _ in range(it):
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        out.append(pts[-1])
        pts = out
    return pts


def build_loop():
    """Closed loop of (x, z) points for the step axles, in travel order, plus segment boundaries."""
    top = _chaikin([(-4.4, -0.45), (-3.4, 0.0), (-2.6, 0.0), (2.6, 3.0), (3.4, 3.0), (4.4, 2.55)], 5)
    top = [(x, z) for x, z in top]
    r = 0.55
    arc1 = [(top[-1][0] + r * math.sin(a), top[-1][1] - r + r * math.cos(a)) for a in [k / 40 * math.pi for k in range(1, 40)]]
    ret = [(x, z - 1.1) for x, z in reversed(top)]
    arc2 = [(ret[-1][0] - r * math.sin(a), ret[-1][1] + r - r * math.cos(a)) for a in [k / 40 * math.pi for k in range(1, 40)]]
    pts = top + arc1 + ret + arc2
    pts = [(x, z + Z0) for x, z in pts]
    cum = [0.0]
    for a, b in zip(pts, pts[1:] + pts[:1]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    L = cum[-1]
    def seglen(seg):
        s = 0
        for a, b in zip(seg, seg[1:]):
            s += math.hypot(b[0] - a[0], b[1] - a[1])
        return s
    b1 = cum[len(top) - 1]
    b2 = cum[len(top) + len(arc1)]
    b3 = cum[len(top) + len(arc1) + len(ret) - 1]
    return pts, cum, L, (b1, b2, b3)


class Loop:
    def __init__(self):
        self.pts, self.cum, self.L, self.bounds = build_loop()

    def at(self, s):
        s %= self.L
        i = max(0, bisect.bisect_right(self.cum, s) - 1)
        i = min(i, len(self.pts) - 1)
        a = self.pts[i]
        b = self.pts[(i + 1) % len(self.pts)]
        seg = self.cum[i + 1] - self.cum[i]
        k = (s - self.cum[i]) / seg if seg > 0 else 0
        return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k

    def flip(self, s):
        """Step rotation about Y: 0 on the visible run, 180 upside down on the return run."""
        s %= self.L
        b1, b2, b3 = self.bounds
        if s < b1:
            return 0.0
        if s < b2:
            return 180.0 * (s - b1) / (b2 - b1)
        if s < b3:
            return 180.0
        return 180.0 + 180.0 * (s - b3) / (self.L - b3)


def _box(size, loc=(0, 0, 0), m=None, name="box"):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True, location=False)
    if m:
        o.data.materials.append(m)
    return o


def _cyl(r, d, loc=(0, 0, 0), rot=(math.radians(90), 0, 0), m=None, v=32, name="cyl"):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d, location=loc, rotation=rot, vertices=v)
    o = bpy.context.object
    o.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)   # bake the tilt into the mesh
    bpy.ops.object.shade_smooth()
    if m:
        o.data.materials.append(m)
    return o


def _join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.object
    o.name = name
    return o


def _tube(points3d, radius, m, name, closed=False):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    sp = cu.splines.new("POLY")
    sp.points.add(len(points3d) - 1)
    for i, p in enumerate(points3d):
        sp.points[i].co = (*p, 1)
    sp.use_cyclic_u = closed
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(m)
    return o


class Model:
    def __init__(self):
        self.loop = Loop()
        n = max(8, round(self.loop.L / PITCH_TARGET))
        self.pitch = self.loop.L / n
        self.n = n
        STEEL = _mat("esc_steel", (0.62, 0.64, 0.7), 1.0, 0.3)
        DARK = _mat("esc_dark", (0.06, 0.05, 0.08), 0.6, 0.35)
        YELLOW = _mat("esc_yellow", (1.0, 0.78, 0.08), 0.0, 0.4)
        self.HERO = _mat("esc_hero", (1.0, 0.18, 0.5), 0.2, 0.35, (1.0, 0.15, 0.45), 0.6)
        RUBBER = _mat("esc_rubber", (0.04, 0.03, 0.05), 0.0, 0.55)
        GEAR = _mat("esc_gear", (0.9, 0.55, 0.2), 1.0, 0.3)
        FLOOR = _mat("esc_floor", (0.72, 0.7, 0.76), 0.8, 0.25)
        CLAD = _mat("esc_clad", (0.35, 0.12, 0.45), 0.6, 0.3)
        GLASS = _mat("esc_glass", (1.0, 0.55, 0.85), 0.0, 0.05, alpha=0.1)
        CHAIN = _mat("esc_chain", (0.35, 0.36, 0.4), 1.0, 0.35)
        # ---- one step, built once, then linked copies
        parts = [_box((TREAD_D, WIDTH, 0.04), (-TREAD_D / 2, 0, TREAD_TOP - 0.02), STEEL, "tread")]
        for k in range(16):  # cleats (the grooves that mesh with the comb)
            y = -WIDTH / 2 + 0.03 + k * (WIDTH - 0.06) / 15
            parts.append(_box((TREAD_D, 0.022, 0.025), (-TREAD_D / 2, y, TREAD_TOP + 0.01), STEEL, "cleat"))
        parts.append(_box((0.03, WIDTH, RISE), (-TREAD_D + 0.015, 0, TREAD_TOP - RISE / 2), STEEL, "riser"))
        for sgn in (-1, 1):
            yoke = _box((TREAD_D, 0.03, 0.22), (-TREAD_D / 2, sgn * (WIDTH / 2 - 0.015), TREAD_TOP - 0.13), DARK, "yoke")
            parts.append(yoke)
        step_body = _join(parts, "step_body")
        edge = _join([_box((0.045, WIDTH, 0.006), (-0.0225, 0, TREAD_TOP + 0.026), YELLOW, "edge"),
                      _box((TREAD_D, 0.04, 0.006), (-TREAD_D / 2, -WIDTH / 2 + 0.02, TREAD_TOP + 0.026), YELLOW, "edge"),
                      _box((TREAD_D, 0.04, 0.006), (-TREAD_D / 2, WIDTH / 2 - 0.02, TREAD_TOP + 0.026), YELLOW, "edge")], "step_edge")
        wheels = _join([_cyl(0.07, 0.05, (0, sgn * 0.6, 0), m=RUBBER, name="cw") for sgn in (-1, 1)] +
                       [_cyl(0.065, 0.05, (-0.3, sgn * 0.68, 0.03), m=RUBBER, name="tw") for sgn in (-1, 1)] +
                       [_cyl(0.015, 1.36, (-0.3, 0, 0.03), m=DARK, name="ax"), _cyl(0.015, 1.2, (0, 0, 0), m=DARK, name="ax2")], "step_wheels")
        proto = [step_body, edge, wheels]
        self.steps = []
        for i in range(n):
            bpy.ops.object.empty_add(location=(0, 0, 0))
            root = bpy.context.object
            root.name = f"step{i}"
            for p in proto:
                c = p.copy()
                bpy.context.collection.objects.link(c)
                c.parent = root
            self.steps.append(root)
        for p in proto:
            p.hide_render = True
            p.hide_viewport = True
        # hero step gets its own pink tread
        hero_body = [c for c in self.steps[0].children if c.name.startswith("step_body")][0]
        hero_body.data = hero_body.data.copy()
        hero_body.data.materials.clear()
        hero_body.data.materials.append(self.HERO)
        # ---- chains: links riding the loop on both sides
        link = _join([_box((0.09, 0.025, 0.035), (0, 0, 0), CHAIN, "link")], "link_proto")
        link.hide_render = True
        self.links = []
        nl = int(self.loop.L / 0.1)
        self.link_pitch = self.loop.L / nl
        for sgn in (-1, 1):
            for k in range(nl):
                c = link.copy()
                bpy.context.collection.objects.link(c)
                c.hide_render = False
                c["side"] = sgn
                c["k"] = k
                self.links.append(c)
        # ---- sprockets (top drive gear, bottom return wheel)
        self.gears = []
        for (cx, cz) in ((4.4, 2.0 + Z0), (-4.4, -1.0 + Z0)):
            for sgn in (-1, 1):
                g = _cyl(0.5, 0.06, (cx, sgn * 0.6, cz), m=GEAR, v=64, name="gear")
                teeth = []
                for k in range(18):
                    a = k / 18 * 2 * math.pi
                    t = _box((0.1, 0.06, 0.06), (cx + 0.54 * math.cos(a), sgn * 0.6, cz + 0.54 * math.sin(a)), GEAR, "tooth")
                    t.rotation_euler = (0, -a, 0)
                    teeth.append(t)
                gj = _join([g] + teeth, "sprocket")   # origin stays at the gear's centre (the cylinder's)
                self.gears.append((gj, (cx, cz)))
        # motor + drive belt
        motor = _box((1.1, 0.8, 0.7), (3.2, 0.45, 1.25 + Z0), _mat("motor", (0.2, 0.22, 0.3), 0.7, 0.35), "motor")
        _cyl(0.32, 0.9, (3.2, 0.45, 1.25 + Z0), (0, math.radians(90), 0), _mat("motor2", (0.25, 0.28, 0.38), 0.8, 0.3), name="motor_can")
        self.belt_pts = [(3.2, 0.9, 1.25 + Z0), (4.4, 0.66, 2.0 + Z0)]
        # ---- trailer track + step-wheel track, generated from the steps' own motion
        trail = []
        for k in range(600):
            s = k / 600 * self.loop.L
            M = self._pose(s)
            trail.append(tuple(M @ Vector((-0.3, 0, 0.03))))
        for sgn in (-1, 1):
            _tube([(x, sgn * 0.68 + sgn * 0.05, z - 0.08) for (x, _, z) in trail], 0.022, STEEL, "trailer_track", closed=True)
            _tube([(x, sgn * 0.6 + sgn * 0.06, z - 0.085) for (x, z) in self.loop.pts[::3]], 0.022, STEEL, "chain_track", closed=True)
        # ---- landings: floor plates with comb teeth
        for (x0, x1, ztop, comb_x, d) in ((3.4, 10.0, 3.0 + TREAD_TOP + Z0, 3.4, -1), (-10.0, -3.4, 0.0 + TREAD_TOP + Z0, -3.4, 1)):
            slab = _box((x1 - x0, 2.4, 0.3), ((x0 + x1) / 2, 0.3, ztop - 0.15), FLOOR, "floor")
            for k in range(16):
                y = -WIDTH / 2 + 0.03 + k * (WIDTH - 0.06) / 15
                t = _box((0.16, 0.018, 0.02), (comb_x + d * 0.06, y, ztop + 0.0), YELLOW, "comb")
        # ---- balustrade (far side glass + handrails), truss and far-side cladding
        top_run = [p for p in self.loop.pts[: len(self.loop.pts) // 2]]
        rail = [(x, z + 1.05) for (x, z) in top_run if -4.0 <= x <= 4.0]
        for sgn in (-1, 1):
            _tube([(x, sgn * 0.78, z) for x, z in rail], 0.045, RUBBER, "handrail")
        pts = [(x, 0.78, z + 0.25) for x, z in rail] + [(x, 0.78, z + 1.0) for x, z in reversed(rail)]
        me = bpy.data.meshes.new("glass")
        verts = [(x, y, z) for x, y, z in pts]
        me.from_pydata(verts, [], [list(range(len(verts)))])
        gl = bpy.data.objects.new("glass", me)
        bpy.context.collection.objects.link(gl)
        gl.data.materials.append(GLASS)
        clad_pts = [(x, 0.95, z + 0.2) for x, z in self.loop.pts]
        me = bpy.data.meshes.new("clad")
        me.from_pydata(clad_pts, [], [list(range(len(clad_pts)))])
        self.clad = bpy.data.objects.new("clad", me)
        bpy.context.collection.objects.link(self.clad)
        self.clad.data.materials.append(CLAD)
        for sgn in (-1, 1):
            y = sgn * 0.95
            chord_top = [(x, y, z - 0.25) for x, z in top_run if -3.6 <= x <= 3.6]
            chord_bot = [(x, y, z - 1.45) for x, z in top_run if -3.6 <= x <= 3.6]
            _tube(chord_top, 0.03, DARK, "chord")
            _tube(chord_bot, 0.03, DARK, "chord")
            for i in range(0, len(chord_top) - 1, max(1, len(chord_top) // 9)):
                a, b = chord_top[i], chord_bot[i]
                _tube([a, b], 0.022, DARK, "vert")
                j = min(len(chord_bot) - 1, i + max(1, len(chord_top) // 9))
                _tube([a, chord_bot[j]], 0.018, DARK, "diag")

    # ------------------------------------------------------------ kinematics
    def _pose(self, s):
        x, z = self.loop.at(s)
        ang = self.loop.flip(s)
        return Matrix.Translation((x, 0, z)) @ Euler((0, math.radians(ang), 0)).to_matrix().to_4x4()

    def apply(self, st):
        travel = float(st.get("travel", 0))
        self.hero = int(st.get("hero", 0))
        self._travel = travel
        for i, root in enumerate(self.steps):
            root.matrix_world = self._pose(i * self.pitch + travel)
        for c in self.links:
            s = c["k"] * self.link_pitch + travel
            x, z = self.loop.at(s)
            x2, z2 = self.loop.at(s + 0.02)
            c.location = (x, c["side"] * 0.6, z - 0.06)
            c.rotation_euler = (0, -math.atan2(z2 - z, x2 - x), 0)
        for gj, (cx, cz) in self.gears:
            gj.rotation_euler = (0, -travel / 0.55, 0)
        self.clad.hide_render = float(st.get("xray", 0)) > 0.5

    def anchor(self, name):
        if name == "hero":
            M = self.steps[0].matrix_world
            return M @ Vector((-TREAD_D / 2, 0, TREAD_TOP))
        if name.startswith("ride:"):
            s = float(name.split(":")[1]) + self._travel
            x, z = self.loop.at(s)
            return Vector((x - TREAD_D / 2, 0, z + TREAD_TOP))
        return Vector((0, 0, 0))
