"""3D explainer: narration -> timed shots + model tracks -> Blender frames -> captions/SFX/music -> mp4.

Script (format "explainer3d"):
  {"format": "explainer3d", "model": "pin_tumbler", "title": ..., "description": ..., "hashtags": [...],
   "voice": "en-US-ChristopherNeural",
   "scenes": [{"say": "...", "key": [caption words in yellow],
               "shots": [{"u": [0, 0.5], "from": {pos, target, lens, fstop}, "to": {...}, "orbit": deg, "shake": 0}],
               "set": [{"u": [0.1, 0.4], "split": 1}, {"u": 0.6, "key_kind": "wrong"}],   # model tracks, u = scene fraction
               "sfx": [{"on": "word", "sound": "clank"}, {"u": 0.3, "sound": "click"}, {"u": [0.2, 0.7], "sound": "click", "n": 5}]}]}
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import skia
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
W, H = 1080, 1920


def plan(script, cfg):
    from ... import audio as A
    A.configure({**cfg, "edge_voice": script.get("voice", cfg.get("edge_voice")), "edge_rate": script.get("rate", cfg.get("edge_rate", "+8%")),
                 "voice": script.get("kokoro_voice", cfg.get("voice", "am_michael"))})
    t = 0.0
    timeline, voice, sfx = [], [], []
    shots, tracks = [], {}
    for i, sc in enumerate(script["scenes"]):
        audio, words = A.tts(sc["say"])
        speech = len(audio) / A.SR
        lead = 0.0 if i == 0 else 0.1
        dur = speech + lead + float(sc.get("tail", 0.25))
        voice.append((t + lead, audio))
        for w in words:
            w["start"] += t + lead
            w["end"] += t + lead
        timeline.append({"start": t, "end": t + dur, "words": words, "scene": sc})
        for sh in sc.get("shots", []):
            u0, u1 = sh.get("u", [0, 1])
            shots.append({**{k: v for k, v in sh.items() if k != "u"}, "start": t + u0 * dur, "end": t + u1 * dur})
        for ev in sc.get("set", []):
            u = ev["u"] if isinstance(ev["u"], list) else [ev["u"], ev["u"]]
            for k, v in ev.items():
                if k == "u":
                    continue
                keys = tracks.setdefault(k, [])
                if isinstance(v, str):
                    keys.append([t + u[0] * dur, v])
                    continue
                prev = keys[-1][1] if keys else v
                keys.append([t + u[0] * dur, prev])
                keys.append([t + u[1] * dur + 1e-3, v])
        for cue in sc.get("sfx", []):
            if cue.get("on"):
                w = next((w for w in words if w["w"].lower().strip(".,!?;:'\"").startswith(cue["on"].lower())), None)
                if w:
                    sfx.append((w["start"] + float(cue.get("offset", 0)), cue["sound"]))
            elif isinstance(cue.get("u"), list):
                n = int(cue.get("n", 1))
                for k in range(n):
                    uu = cue["u"][0] + (cue["u"][1] - cue["u"][0]) * (k / max(1, n - 1))
                    sfx.append((t + uu * dur, cue["sound"]))
            elif "u" in cue:
                sfx.append((t + float(cue["u"]) * dur, cue["sound"]))
        if i:
            sfx.append((t - 0.08, "whoosh"))
        t += dur
    for k in tracks:
        tracks[k].sort(key=lambda kv: kv[0])
    return timeline, voice, sfx, shots, tracks, t


def render(script, out_path, cfg, preview=False, frames_dir=None):
    from ... import audio as A
    from .. import disco as D
    from ..lit_stage import caption_groups, draw_caption
    fps = 24
    # On CI the plan (voice + timings) is made once and shared, so every render machine uses identical timing.
    plan_file = os.environ.get("X3D_PLAN_FILE")
    if plan_file and Path(plan_file).exists():
        import pickle
        timeline, voice, sfx, shots, tracks, total = pickle.loads(Path(plan_file).read_bytes())
    else:
        timeline, voice, sfx, shots, tracks, total = plan(script, cfg)
        if plan_file:
            import pickle
            Path(plan_file).parent.mkdir(parents=True, exist_ok=True)
            Path(plan_file).write_bytes(pickle.dumps((timeline, voice, sfx, shots, tracks, total)))
            if os.environ.get("X3D_PLAN_ONLY"):
                print(f"[x3d] plan saved: {total:.2f}s")
                return None
    n = int(total * fps)
    work = Path(frames_dir or tempfile.mkdtemp(prefix="x3d_"))
    work.mkdir(parents=True, exist_ok=True)
    job = {"model": script.get("model", "pin_tumbler"), "fps": fps,
           "res": [360, 640] if preview else script.get("res", [720, 1280]),
           "samples": 4 if preview else int(script.get("samples", 16)),
           "out_dir": str(work / "frames"), "frames": n, "shots": shots, "tracks": tracks}
    for k in ("pedestal", "speed0", "travel0", "lights_scale", "raytrace"):
        if k in script:
            job[k] = script[k]
    if preview:
        job["only"] = list(range(0, n, fps // 2))
    # Parallel rendering on CI: X3D_CHUNK="i/K" renders only that slice of frames and stops;
    # X3D_ASSEMBLE=1 skips Blender and builds the video from frames the chunk jobs rendered.
    chunk = os.environ.get("X3D_CHUNK")
    if chunk:
        i, k = map(int, chunk.split("/"))
        job["only"] = list(range(i * n // k, (i + 1) * n // k))
    (work / "job.json").write_text(json.dumps(job))
    if os.environ.get("X3D_ASSEMBLE"):
        fdir = work / "frames"
        have = sorted(int(p.stem[1:]) for p in fdir.glob("f*.png"))
        missing = [fi for fi in range(n) if not (fdir / f"f{fi:05d}.png").exists()]
        print(f"[x3d] assembling {n} frames ({len(have)} rendered, {len(missing)} filled from neighbours)")
        if len(missing) > max(6, n // 50):
            raise RuntimeError(f"too many missing frames: {missing[:20]}")
        import shutil
        for fi in missing:
            near = min(have, key=lambda h: abs(h - fi))
            shutil.copy(fdir / f"f{near:05d}.png", fdir / f"f{fi:05d}.png")
    done = sorted((work / "frames").glob("*.png")) if (work / "frames").exists() else []
    if not os.environ.get("X3D_ASSEMBLE") and len(done) < len(job.get("only") or range(n)):
        subprocess.run([sys.executable, "-m", "pipeline.render.x3d.blender_job", str(work / "job.json")], cwd=str(ROOT), check=True)
    if preview or chunk:
        return work
    # audio: deep narration + mechanical SFX + quiet ambient bed
    mixed = A.mix(total, voice, sfx, music_seed=7, music_gain=float(script.get("music_gain", 0.14)))
    wav = str(work / "mix.wav")
    A.write_wav(wav, mixed)
    words = [w for seg in timeline for w in seg["words"]]
    groups = caption_groups(words)
    keys = {k.lower() for seg in timeline for k in seg["scene"].get("key", [])}
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-i", wav, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    samp = skia.SamplingOptions(skia.CubicResampler.Mitchell())
    for fi in range(n):
        t = fi / fps
        src = skia.Image.open(str(work / "frames" / f"f{fi:05d}.png"))
        surf = skia.Surface(W, H)
        c = surf.getCanvas()
        c.drawImageRect(src, skia.Rect.MakeWH(W, H), samp)
        draw_caption(c, groups, t, keys)
        img = Image.fromarray(np.ascontiguousarray(surf.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType)[:, :, :3]))
        si = next((i for i, s in enumerate(timeline) if s["start"] <= t < s["end"]), len(timeline) - 1)
        seg = timeline[si]
        D.progress_segments(img, len(timeline), si, (t - seg["start"]) / (seg["end"] - seg["start"]))
        enc.stdin.write(img.tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return {"duration": total, "path": out_path}


if __name__ == "__main__":
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    sc = json.loads(Path(sys.argv[1]).read_text())
    if len(sys.argv) > 3 and sys.argv[3] == "preview":
        print(render(sc, sys.argv[2], cfg, preview=True, frames_dir=sys.argv[4] if len(sys.argv) > 4 else None))
    else:
        print(render(sc, sys.argv[2], cfg, frames_dir=sys.argv[3] if len(sys.argv) > 3 else None))
