"""Pin-tumbler lock model for the 3D explainer (runs inside Blender / bpy).

Axis: the lock lies along X, the key enters from +X. The plug's top (the shear line) is at z = SHEAR.
State parameters (all tweenable from the script):
  key_in       0 = key fully out (hidden far right), 1 = fully inserted
  key_kind     "right" or "wrong"
  plug_rot     degrees the plug (and key) turn about X; blocked locks jiggle a few degrees
  split        0 = lock closed, 1 = front half slid away (cutaway view)
  shear_glow   0..1 glowing shear line
  bad_glow     0..1 red glow on the pin that blocks the wrong key
  key_solo     0..1 show the key floating above the lock for a beauty orbit (key_spin degrees)
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

SHEAR = 0.6
XS = [-1.1, -0.55, 0.0, 0.55, 1.1]
TIP_IN = -1.4                    # key tip x when fully inserted
RIGHT = [0.22, 0.08, 0.30, 0.14, 0.26]
WRONG = [0.22, 0.08, 0.42, 0.14, 0.26]   # pin 3 lifted too high
KEY_PINS = [SHEAR - h for h in RIGHT]
DRIVER = 0.40
CHAMBER_TOP = 2.0
BAD = 2


def _mat(name, col, metal=0.0, rough=0.4, emit=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def _add(o, m):
    o.data.materials.clear()
    o.data.materials.append(m)
    return o


def _cyl(r, d, loc, rot=(0, 0, 0), m=None, v=96, name=None):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d, location=loc, rotation=rot, vertices=v)
    o = bpy.context.object
    if name:
        o.name = name
    bpy.ops.object.shade_smooth()
    if m:
        _add(o, m)
    return o


def _box(size, loc, m=None, name=None):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    if name:
        o.name = name
    if m:
        _add(o, m)
    return o


def _bool(o, cutter, op="DIFFERENCE"):
    md = o.modifiers.new("b", "BOOLEAN")
    md.object = cutter
    md.operation = op
    md.solver = "EXACT"
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=md.name)


def _hide(o):
    o.hide_render = True
    o.hide_viewport = True


def _dup(o, name):
    n = o.copy()
    n.data = o.data.copy()
    n.name = name
    bpy.context.collection.objects.link(n)
    return n


def _halves(o, name):
    """Split an object into a back half (y>0, stays) and a front half (y<0, slides away)."""
    front = _dup(o, name + "_front")
    cutter = _box((8, 4, 8), (0, -2, 0), name=name + "_cut")
    _bool(o, cutter, "DIFFERENCE")
    _bool(front, cutter, "INTERSECT")
    _hide(cutter)
    return o, front


def _key_profile(h):
    """Top edge of the key blade as (u, z) points, u = distance from the tip."""
    us = [x - TIP_IN for x in XS]
    pts = [(0.0, -0.05), (0.12, 0.04)]
    for u, hh in zip(us, h):
        pts += [(u - 0.07, hh), (u + 0.07, hh)]
    pts += [(2.72, 0.36), (2.95, 0.46)]
    return pts


def key_top(h, u):
    pts = _key_profile(h)
    if u < 0 or u > 2.95:
        return None
    for (u0, z0), (u1, z1) in zip(pts, pts[1:]):
        if u0 <= u <= u1:
            return z0 + (z1 - z0) * (u - u0) / max(1e-6, u1 - u0)
    return pts[-1][1]


def _key_mesh(name, h, m_blade, m_bow):
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    prof = _key_profile(h)
    outline = [(0.0, -0.42)] + prof + [(3.1, 0.46), (3.1, -0.42)]
    t = 0.07
    vf = [bm.verts.new((u, -t, z)) for u, z in outline]
    vb = [bm.verts.new((u, t, z)) for u, z in outline]
    bm.faces.new(vf)
    bm.faces.new(list(reversed(vb)))
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((vf[i], vf[j], vb[j], vb[i]))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    blade = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(blade)
    _add(blade, m_blade)
    bev = blade.modifiers.new("bv", "BEVEL")
    bev.width = 0.012
    bev.segments = 2
    # bow (head of the key) with a hole
    bow = _cyl(0.72, 0.16, (3.75, 0, 0.02), (math.radians(90), 0, 0), m_bow, name=name + "_bow")
    hole = _cyl(0.16, 0.5, (4.1, 0, 0.02), (math.radians(90), 0, 0), name=name + "_hole")
    _bool(bow, hole)
    _hide(hole)
    bow.parent = blade
    bow.location = (3.75, 0, 0.02)
    return blade


class Lock:
    def __init__(self):
        self.BRASS = _mat("brass", (0.86, 0.56, 0.2), 1.0, 0.26)
        self.PLUG = _mat("plug", (0.95, 0.7, 0.32), 1.0, 0.3)
        self.STEEL = _mat("steel", (0.78, 0.8, 0.85), 1.0, 0.2)
        self.NICKEL = _mat("nickel", (0.82, 0.84, 0.88), 1.0, 0.18)
        self.BOW = _mat("bow", (1.0, 0.2, 0.5), 0.0, 0.32)
        self.SPRING = _mat("spring", (0.6, 0.62, 0.68), 1.0, 0.25)
        self.GLOW = _mat("shear", (1.0, 0.55, 0.15), 0.0, 0.5, (1.0, 0.5, 0.1), 0.0)
        self.pin_mats = [_mat(f"kpin{i}", (0.95, 0.62, 0.22), 1.0, 0.25, (1.0, 0.1, 0.1), 0.0) for i in range(5)]
        # housing: round body + tower holding the pin chambers
        body = _cyl(1.0, 3.0, (0, 0, 0), (0, math.radians(90), 0), self.BRASS, name="housing")
        tower = _box((3.0, 1.0, 1.9), (0, 0, 1.25), self.BRASS)
        _bool(body, tower, "UNION")
        _hide(tower)
        bore = _cyl(0.615, 3.4, (0, 0, 0), (0, math.radians(90), 0), name="bore")
        _bool(body, bore)
        _hide(bore)
        for x in XS:
            ch = _cyl(0.17, 1.6, (x, 0, 1.25), name="chamber")
            _bool(body, ch)
            _hide(ch)
        bv = body.modifiers.new("bv", "BEVEL")
        bv.width = 0.03
        bv.segments = 2
        bv.limit_method = "ANGLE"
        # plug with keyway and pin holes
        plug = _cyl(0.6, 3.1, (0.05, 0, 0), (0, math.radians(90), 0), self.PLUG, name="plug")
        kw = _box((3.6, 0.17, 0.95), (0.2, 0, -0.03))
        _bool(plug, kw)
        _hide(kw)
        for x in XS:
            hcl = _cyl(0.165, 1.0, (x, 0, 0.3), name="hole")
            _bool(plug, hcl)
            _hide(hcl)
        self.house_back, self.house_front = _halves(body, "housing")
        self.plug_back, self.plug_front = _halves(plug, "plug")
        for o in (self.house_back, self.house_front, self.plug_back, self.plug_front):
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.shade_smooth()
        # plug pivot so it can rotate about X with everything inside it
        bpy.ops.object.empty_add(location=(0, 0, 0))
        self.pivot = bpy.context.object
        self.pivot.name = "plug_pivot"
        for o in (self.plug_back, self.plug_front):
            o.parent = self.pivot
        # pins + springs
        self.kpins, self.dpins, self.springs = [], [], []
        for i, x in enumerate(XS):
            L = KEY_PINS[i]
            kp = _cyl(0.145, L, (x, 0, L / 2), m=self.pin_mats[i], v=48, name=f"kpin{i}")
            bv = kp.modifiers.new("bv", "BEVEL")
            bv.width = 0.05
            bv.segments = 4
            self.kpins.append(kp)
            dp = _cyl(0.145, DRIVER, (x, 0, L + DRIVER / 2), m=self.STEEL, v=48, name=f"dpin{i}")
            bv = dp.modifiers.new("bv", "BEVEL")
            bv.width = 0.03
            bv.segments = 3
            self.dpins.append(dp)
            self.springs.append(self._spring(x, i))
        # glowing shear line strip on the cut face
        self.shear = _box((3.1, 0.01, 0.03), (0.05, -0.005, SHEAR), self.GLOW, name="shear")
        # keys
        self.key_r = _key_mesh("key_right", RIGHT, self.NICKEL, self.BOW)
        self.key_w = _key_mesh("key_wrong", WRONG, self.NICKEL, _mat("bow2", (0.3, 0.6, 1.0), 0.0, 0.32))
        # a front door the lock sits in (for the opening and closing shots)
        DOOR = _mat("door", (0.2, 0.13, 0.42), 0.0, 0.45)
        PANEL = _mat("panel", (0.27, 0.18, 0.52), 0.0, 0.4)
        door = _box((0.22, 9.0, 13.0), (1.74, 0, 0.5), DOOR, name="door")
        hole = _cyl(0.95, 1.0, (1.74, 0, 0), (0, math.radians(90), 0), name="dhole")
        _bool(door, hole)
        _hide(hole)
        self.door = [door]
        for (py, pz, w, h_) in ((-2.0, 3.4, 2.6, 3.6), (2.0, 3.4, 2.6, 3.6), (-2.0, -3.0, 2.6, 4.4), (2.0, -3.0, 2.6, 4.4)):
            self.door.append(_box((0.06, w, h_), (1.87, py, pz), PANEL))
        rose = _cyl(1.18, 0.08, (1.88, 0, 0), (0, math.radians(90), 0), self.BRASS, name="rose")
        rh = _cyl(0.63, 0.4, (1.88, 0, 0), (0, math.radians(90), 0), name="rh")
        _bool(rose, rh)
        _hide(rh)
        self.door.append(rose)
        lever = _box((0.5, 2.2, 0.32), (2.05, -1.2, 2.1), self.BRASS, name="lever")
        bv = lever.modifiers.new("bv", "BEVEL")
        bv.width = 0.12
        bv.segments = 4
        self.door.append(lever)
        self.door.append(_cyl(0.42, 0.35, (1.95, 0, 2.1), (0, math.radians(90), 0), self.BRASS))
        bpy.ops.object.empty_add(location=(0, 0, 0))
        self.key_pivot = bpy.context.object
        for k in (self.key_r, self.key_w):
            k.parent = self.key_pivot

    def _spring(self, x, i):
        cu = bpy.data.curves.new(f"spring{i}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.022
        cu.bevel_resolution = 3
        sp = cu.splines.new("POLY")
        turns, n = 9, 9 * 16
        sp.points.add(n - 1)
        for k in range(n):
            a = k / 16 * 2 * math.pi
            sp.points[k].co = (0.11 * math.cos(a), 0.11 * math.sin(a), -k / (n - 1), 1)   # unit length, hangs down from 0
        o = bpy.data.objects.new(f"spring{i}", cu)
        bpy.context.collection.objects.link(o)
        o.location = (x, 0, CHAMBER_TOP)
        o.data.materials.append(self.SPRING)
        return o

    # ------------------------------------------------------------ state
    def apply(self, s):
        kind = s.get("key_kind", "right")
        h = RIGHT if kind == "right" else WRONG
        key = self.key_r if kind == "right" else self.key_w
        other = self.key_w if kind == "right" else self.key_r
        other.hide_render = True
        for ch in other.children:
            ch.hide_render = True
        key.hide_render = False
        for ch in key.children:
            ch.hide_render = False
        key_in = float(s.get("key_in", 0))
        tip = TIP_IN + (1 - key_in) * 4.8
        solo = float(s.get("key_solo", 0))
        rot = math.radians(float(s.get("plug_rot", 0)))
        # key: inserted along X, or floating above for a beauty orbit
        key.location = (tip, 0, 0)
        self.key_pivot.location = (0, 0, solo * 3.2)
        self.key_pivot.rotation_euler = (rot, 0, math.radians(float(s.get("key_spin", 0))) * solo)
        self.pivot.rotation_euler = (rot, 0, 0)
        # pins ride on the key profile
        for i, x in enumerate(XS):
            u = x - tip
            top = key_top(h, u) if solo < 0.5 else None
            bottom = max(0.0, top) if top is not None else 0.0
            L = KEY_PINS[i]
            kp, dp, spg = self.kpins[i], self.dpins[i], self.springs[i]
            # key pins turn with the plug (they live in it); driver pins only do when they're fully above the gap
            c, sn = math.cos(rot), math.sin(rot)
            zc = bottom + L / 2
            kp.location = (x, -sn * zc, c * zc)
            kp.rotation_euler = (rot, 0, 0)
            dz = bottom + L + DRIVER / 2
            dp.location = (x, 0, dz)
            dp.rotation_euler = (0, 0, 0)
            spg.scale = (1, 1, max(0.2, CHAMBER_TOP - (bottom + L + DRIVER)))
            self.pin_mats[i].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = \
                float(s.get("bad_glow", 0)) * 6.0 if (i == BAD and kind == "wrong") else 0.0
        self.GLOW.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = float(s.get("shear_glow", 0)) * 14.0
        self.shear.hide_render = float(s.get("shear_glow", 0)) < 0.02
        # cutaway: the front half slides toward the camera and drops away
        sp = float(s.get("split", 0))
        for o in (self.house_front,):
            o.location = (0, -1.4 * sp, -6.0 * sp * sp)   # slides out and drops away below the pedestal
            o.hide_render = sp > 0.98
        self.plug_front.location = (0, -1.4 * sp, -6.0 * sp * sp)
        self.plug_front.hide_render = sp > 0.98
        dv = float(s.get("door", 0))
        for o in self.door:
            o.hide_render = dv < 0.5
