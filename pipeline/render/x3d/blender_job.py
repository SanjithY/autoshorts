"""Render a 3D explainer's frames with Blender (bpy). Run as: python -m pipeline.render.x3d.blender_job job.json

job.json:
  {"model": "pin_tumbler", "fps": 24, "res": [720, 1280], "samples": 12, "out_dir": "...", "frames": N,
   "shots": [{"start": s, "end": e, "from": {"pos": [..], "target": [..], "lens": 50, "fstop": 2.8},
              "to": {...}, "orbit": 40, "shake": 0.0}],
   "tracks": {"key_in": [[t, value], ...], ...},     # tweened model parameters (absolute seconds)
   "only": [frame indices] optional (previews)}
"""
from __future__ import annotations

import importlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


def ease(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def track_value(keys, t, default):
    if not keys:
        return default
    if isinstance(keys[0][1], str):  # discrete values (e.g. which key)
        v = keys[0][1]
        for kt, kv in keys:
            if kt <= t:
                v = kv
        return v
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * ease((t - t0) / max(1e-6, t1 - t0))
    return keys[-1][1]


def mat(name, col, metal=0.0, rough=0.4, emit=None, strength=0.0):
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


def studio():
    """Signature set: a curved pink-to-purple cyclorama, glossy floor, a pedestal ringed with neon."""
    sc = bpy.context.scene
    # cyclorama: floor + curved back wall in one mesh
    import bmesh
    me = bpy.data.meshes.new("cyc")
    bm = bmesh.new()
    prof = [(-14, -2.0)]
    R = 6.0
    for k in range(17):
        a = k / 16 * math.pi / 2
        prof.append((8 - R * math.cos(a) * 0 + R * math.sin(a), -2.0 + R - R * math.cos(a)))
    prof = [(-14, -2.0), (2, -2.0)] + [(2 + R * math.sin(k / 16 * math.pi / 2), -2.0 + R - R * math.cos(k / 16 * math.pi / 2)) for k in range(1, 17)] + [(8, 14)]
    rows = []
    for y, z in prof:
        rows.append([bm.verts.new((x, y, z)) for x in (-20, 20)])
    for r0, r1 in zip(rows, rows[1:]):
        bm.faces.new((r0[0], r0[1], r1[1], r1[0]))
    bm.to_mesh(me)
    bm.free()
    cyc = bpy.data.objects.new("cyc", me)
    sc.collection.objects.link(cyc)
    m = bpy.data.materials.new("cycmat")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.35
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.2
    ramp.color_ramp.elements[0].color = (0.16, 0.04, 0.22, 1)
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = (0.9, 0.12, 0.42, 1)
    mp = nt.nodes.new("ShaderNodeMapRange")
    mp.inputs["From Min"].default_value = -2.0
    mp.inputs["From Max"].default_value = 12.0
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mp.inputs["Value"])
    nt.links.new(mp.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    cyc.data.materials.append(m)
    # pedestal with a neon ring
    bpy.ops.mesh.primitive_cylinder_add(radius=2.6, depth=0.4, location=(0, 0, -1.8), vertices=128)
    ped = bpy.context.object
    bpy.ops.object.shade_smooth()
    ped.data.materials.append(mat("ped", (0.08, 0.04, 0.1), 0.2, 0.15))
    bpy.ops.mesh.primitive_torus_add(major_radius=2.62, minor_radius=0.04, location=(0, 0, -1.6), major_segments=128)
    ring = bpy.context.object
    ring.data.materials.append(mat("neon", (1, 0.3, 0.6), 0, 0.5, (1.0, 0.25, 0.6), 18.0))
    bpy.ops.mesh.primitive_torus_add(major_radius=2.62, minor_radius=0.03, location=(0, 0, -2.0), major_segments=128)
    bpy.context.object.data.materials.append(mat("neon2", (1, 0.6, 0.2), 0, 0.5, (1.0, 0.55, 0.15), 10.0))

    def light(kind, loc, energy, col, size=2.0, target=(0, 0, 0)):
        bpy.ops.object.light_add(type=kind, location=loc)
        l = bpy.context.object
        l.data.energy = energy
        l.data.color = col
        if kind == "AREA":
            l.data.size = size
        d = Vector(target) - l.location
        l.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return l
    light("AREA", (-4, -5, 6), 1400, (1.0, 0.86, 0.72), 4)       # warm key
    light("AREA", (5, 3, 3), 1100, (1.0, 0.25, 0.62), 3)          # pink rim
    light("AREA", (-5, 3, 2), 700, (1.0, 0.55, 0.18), 3)          # orange rim
    light("AREA", (0, -6, -1), 260, (0.55, 0.4, 1.0), 6)          # soft purple fill from below
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.12, 0.04, 0.16, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.5


def main(job_path):
    job = json.loads(Path(job_path).read_text())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = job.get("res", [720, 1280])
    sc.render.engine = "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = int(job.get("samples", 12))
    for attr, val in (("use_shadows", True), ("use_raytracing", bool(job.get("raytrace", False))), ("use_gtao", True)):
        try:
            setattr(sc.eevee, attr, val)
        except Exception:
            pass
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy" if "AgX - Punchy" in [l.name for l in []] else sc.view_settings.look
    studio()
    model = importlib.import_module(f"pipeline.render.x3d.{job['model']}")
    rig = model.Lock() if job["model"] == "pin_tumbler" else model.Model()
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    sc.camera = cam
    cam.data.dof.use_dof = True
    fps = job.get("fps", 24)
    out = Path(job["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    frames = job.get("only") or range(job["frames"])
    tracks = job.get("tracks", {})
    t_start = time.time()
    for fi in frames:
        t = fi / fps
        shot = next((s for s in job["shots"] if s["start"] <= t < s["end"]), job["shots"][-1])
        u = (t - shot["start"]) / max(1e-6, shot["end"] - shot["start"])
        e = ease(u) if shot.get("ease", True) else u
        a, b = shot["from"], shot.get("to", shot["from"])
        lerp3 = lambda p, q: Vector(p).lerp(Vector(q), e)
        tgt = lerp3(a["target"], b.get("target", a["target"]))
        pos = lerp3(a["pos"], b.get("pos", a["pos"]))
        orb = math.radians(shot.get("orbit", 0) * e)
        if orb:
            rel = pos - tgt
            rel.rotate(__import__("mathutils").Euler((0, 0, orb)))
            pos = tgt + rel
        sh = shot.get("shake", 0.0)
        if sh:
            pos += Vector((math.sin(t * 13) * sh, math.cos(t * 11) * sh, math.sin(t * 17) * sh))
        cam.location = pos
        cam.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = a.get("lens", 50) + (b.get("lens", a.get("lens", 50)) - a.get("lens", 50)) * e
        cam.data.dof.focus_distance = (tgt - pos).length
        cam.data.dof.aperture_fstop = a.get("fstop", 2.8)
        state = {k: track_value(v, t, 0) for k, v in tracks.items()}
        rig.apply(state)
        sc.render.filepath = str(out / f"f{fi:05d}.png")
        bpy.ops.render.render(write_still=True)
        if fi % 24 == 0:
            el = time.time() - t_start
            print(f"[x3d] frame {fi}/{job['frames']}  {el:.0f}s elapsed", flush=True)


if __name__ == "__main__":
    main(sys.argv[-1])
