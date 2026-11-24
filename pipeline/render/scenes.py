"""Animated scene renderers + the timeline that turns a script JSON into a finished video."""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from .. import audio as A
from .core import (BlankBackground, BLACK, CAPTION_Y, GREEN, H, HOT, ORANGE, PINK, TEAL, W, WHITE, YELLOW, FPS,
                   Encoder, SynthwaveBackground, VideoBackground, caption_chunks, draw_caption,
                   draw_progress, ease_out_back, ease_out_cubic, paste, prog, rounded_box, star_points,
                   text_sprite)

CENTER_Y = 720
MIN_DUR = {"stat": 2.6, "bars": 3.4, "versus": 3.6, "stars": 3.0, "hook": 1.6, "quiz_a": 2.2}
SCENE_SFX = {"stick": "whoosh", "hook": "boom", "stat": "whoosh", "bars": "whoosh", "versus": "whoosh",
             "list_item": "whoosh", "stars": "siren", "quiz_q": "whoosh", "quiz_a": "ding",
             "text": "whoosh", "outro": "pop"}


# ---------------------------------------------------------------- scene drawers (Disco style)
from . import disco as D
from .disco import CENTER_Y as CY


def _hl(s):
    return tuple(s.get("highlight", []))


def draw_hook(f, s, lt, d):
    p = ease_out_back(lt / 0.3)
    spr = D.gtext(s["text"].upper(), "display", 168, 960, _hl(s), stroke=0)
    shake = math.sin(lt * 60) * 8 * max(0, 1 - lt / 0.3)
    paste(f, spr, W / 2 + shake, CY, 0.55 + 0.45 * p)
    k = ease_out_cubic((lt - 0.15) / 0.4)
    if k > 0:
        bar = D.gradient(int(520 * k) + 2, 12).convert("RGBA")
        bar.putalpha(D.round_mask(bar.width, 12, 6))
        paste(f, bar, W / 2, CY + spr.height / 2 + 20, 1)


def draw_text(f, s, lt, d):
    k = ease_out_cubic(lt / 0.35)
    c = D.text_card(s["text"], 1000, 3, _hl(s))
    paste(f, c, W / 2, CY + 40 * (1 - k), 1, alpha=k)
    if s.get("sub"):
        sp = D.pill(s["sub"], 38, grad=True, dot=False)
        paste(f, sp, W / 2, CY + c.height / 2 + 60, ease_out_back(prog(lt, 0.3, 0.3)))


def _fmt(v, s):
    dec = int(s.get("decimals", 0))
    num = f"{v:,.{dec}f}"
    return f"{s.get('prefix', '')}{num}{s.get('suffix', '')}"


def draw_stat(f, s, lt, d):
    t_count = min(1.6, d * 0.55)
    cnt = ease_out_cubic(prog(lt, 0.1, t_count))
    done = cnt >= 0.999
    val = float(s["value"]) if done else float(s["value"]) * cnt
    c = D.card(1000, 470)
    paste(f, c, W / 2, CY, 1, alpha=min(1, lt / 0.2))
    paste(f, D.pill(s.get("label", ""), 40), W / 2, CY - 160, 1, alpha=min(1, lt / 0.25))
    num = D.gtext(_fmt(val, s), "display", 210, 960, all_grad=done)
    pulse = 1 + (0.1 * math.exp(-(lt - 0.1 - t_count) * 8) if done else 0)
    paste(f, num, W / 2, CY + 30, pulse)
    if s.get("sub"):
        sub = text_sprite(s["sub"].upper(), "black", 40, (200, 200, 215), 0, BLACK, 900, False)
        paste(f, sub, W / 2, CY + 185, 1, alpha=prog(lt, 0.9, 0.3))


def draw_bars(f, s, lt, d):
    items = s["items"][:4]
    n = len(items)
    ch = 150 + n * 170
    top = CY - ch / 2
    paste(f, D.card(1000, int(ch)), W / 2, CY, 1, alpha=min(1, lt / 0.2))
    paste(f, D.pill(s.get("title", ""), 38), W / 2, top + 70, 1)
    mx = max(float(i["value"]) for i in items) or 1
    hi = s.get("highlight", 0)
    dr = ImageDraw.Draw(f)
    for k, it in enumerate(items):
        y = top + 150 + k * 170
        g = ease_out_cubic(prog(lt, 0.25 + k * 0.3, 0.7))
        lab = text_sprite(it["label"].upper(), "black", 40, WHITE, 0, BLACK, 800, False)
        paste(f, lab, 100 + lab.width / 2, y + 20, 1, alpha=prog(lt, 0.2 + k * 0.3, 0.2))
        bw = int(760 * float(it["value"]) / mx * g)
        if bw > 6:
            if k == hi:
                bar = D.gradient(bw, 64).convert("RGBA")
                bar.putalpha(D.round_mask(bw, 64, 20))
                f.paste(bar, (100, int(y + 60)), bar)
            else:
                dr.rounded_rectangle((100, y + 60, 100 + bw, y + 124), 20, fill=(125, 105, 180))
        if g > 0.6:
            vs = text_sprite(str(it.get("display", it["value"])), "display", 58, WHITE, 0, BLACK, 300, True)
            x = 100 + bw + 20 + vs.width / 2
            if x + vs.width / 2 > W - 50:
                x = 100 + bw - vs.width / 2 - 16
            paste(f, vs, x, y + 92, 1)


def draw_versus(f, s, lt, d):
    p = ease_out_back(lt / 0.35)
    lp = D.pill(s.get("left", "A"), 52, grad=False, dot=False, kind="black")
    rp = D.pill(s.get("right", "B"), 52, grad=True, dot=False, kind="black")
    paste(f, lp, 270 - 420 * (1 - p), 430, 1)
    paste(f, rp, 810 + 420 * (1 - p), 430, 1)
    vs = D.badge("VS", 120, 70)
    paste(f, vs, W / 2, 430, ease_out_back(prog(lt, 0.2, 0.3)))
    for k, row in enumerate(s.get("rows", [])[:4]):
        a = prog(lt, 0.5 + k * 0.45, 0.25)
        if a <= 0:
            continue
        y = 600 + k * 175
        paste(f, D.card(1000, 150, accent=False), W / 2, y, 0.92 + 0.08 * ease_out_back(a), a)
        lab = text_sprite(row["label"].upper(), "black", 32, (200, 200, 215), 0, BLACK, 380, False)
        paste(f, lab, W / 2, y, 1, a)
        lv = text_sprite(str(row["l"]), "display", 64, WHITE, 0, BLACK, 300, True)
        rv = D.gtext(str(row["r"]), "display", 64, 300, all_grad=True)
        paste(f, lv, 190, y, 1, a)
        paste(f, rv, 890, y, 1, a)


def draw_list_item(f, s, lt, d):
    k = ease_out_cubic(lt / 0.35)
    c = D.text_card(s["text"], 1000, 3, _hl(s), sizes=(84, 76, 68, 60, 52), left=210, min_h=260)
    paste(f, c, W / 2, CY + 40 * (1 - k), 1, alpha=k)
    sb = ease_out_back(min(1, max(0, (lt - 0.05) / 0.4)))
    paste(f, D.badge(f"#{s['n']}", 196, 120), 40 + 30 + 98, CY + 40 * (1 - k), 0.4 + 0.6 * sb, rot=-8 * (1 - sb))


def draw_stars(f, s, lt, d):
    n = int(s.get("n", 6))
    paste(f, D.card(1000, 420), W / 2, CY, 1, alpha=min(1, lt / 0.2))
    dr = ImageDraw.Draw(f)
    y = CY - 80
    for k in range(6):
        cx = 175 + k * 146
        on = lt > 0.3 + k * 0.25 and k < n
        a = ease_out_back(prog(lt, 0.3 + k * 0.25, 0.2)) if on else 1
        flash = on and k == n - 1 and int(lt * 6) % 2 == 0 and lt > 0.3 + n * 0.25
        col = (255, 255, 255) if flash else (D.PINK if k % 2 == 0 else D.ORANGE) if on else (40, 36, 60)
        D.star_shape(dr, cx, y, 56 * a, col, outline=(255, 255, 255) if on else (90, 90, 110))
    t = D.gtext(s["text"].upper(), "display", 96, 900, _hl(s))
    paste(f, t, W / 2, CY + 100, 1, alpha=prog(lt, 0.2, 0.25))


def _options(f, s, lt, reveal=None, top=740):
    for k, o in enumerate(s["options"][:3]):
        a = prog(lt, 0.3 + k * 0.22, 0.2)
        y = top + k * 170
        ok = reveal is not None and k == reveal
        dim = reveal is not None and not ok
        c = D.card(940, 140, accent=False, fill=(20, 110, 70, 230) if ok else (10, 10, 18, 120 if dim else 205))
        paste(f, c, W / 2, y, 0.92 + 0.08 * ease_out_back(a), a)
        paste(f, D.badge("ABC"[k], 96, 60), 140, y, 1, a)
        t = text_sprite(str(o).upper(), "black", 52, WHITE if not dim else (160, 160, 175), 0, BLACK, 680, False)
        paste(f, t, 220 + t.width / 2, y, 1, a)


def draw_quiz_q(f, s, lt, d):
    q = D.text_card(s["question"], 1000, 3, _hl(s), sizes=(68, 62, 56, 50))
    paste(f, q, W / 2, 480, ease_out_back(min(1, lt / 0.3)))
    _options(f, s, lt)
    cd = s.get("_countdown_start")
    if cd is not None and lt >= cd:
        rem = max(0.0, 3 - (lt - cd))
        dr = ImageDraw.Draw(f)
        cx, cy, r = W / 2, 1235, 70
        dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(10, 10, 18))
        dr.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * rem / 3, fill=D.PINK, width=14)
        num = text_sprite(str(math.ceil(rem) if rem > 0 else 0), "display", 96, WHITE, 0, BLACK, 300)
        paste(f, num, cx, cy, 1 + 0.15 * (1 - (rem % 1)))


def draw_quiz_a(f, s, lt, d):
    q = D.text_card(s.get("question", ""), 1000, 3, (), sizes=(68, 62, 56, 50))
    paste(f, q, W / 2, 480, 1)
    _options(f, s, 9, reveal=int(s["answer"]))
    paste(f, D.pill("CORRECT: " + "ABC"[int(s["answer"])], 40, grad=True, dot=False), W / 2, 1235,
          ease_out_back(prog(lt, 0.1, 0.3)))


def draw_outro(f, s, lt, d):
    spr = D.gtext(s["text"].upper(), "display", 124, 940, _hl(s))
    paste(f, spr, W / 2, CY - 40, ease_out_back(lt / 0.3))
    if s.get("cta"):
        cta = D.pill(s["cta"], 46, grad=True, dot=False)
        paste(f, cta, W / 2, CY + spr.height / 2 + 70, (1 + 0.05 * math.sin(lt * 6)) * ease_out_back(prog(lt, 0.25, 0.3)))


def draw_stick(f, s, lt, d):
    from PIL import Image as _I
    from .stick import World
    world = s.setdefault("_world_ref", {}).get("w")
    if world is None:
        world = World()
        s["_world_ref"]["w"] = world
    arr = world.frame(s, lt, d, s.get("_key"))
    f.paste(_I.fromarray(arr))


DRAW = {"stick": draw_stick, "hook": draw_hook, "text": draw_text, "stat": draw_stat, "bars": draw_bars,
        "versus": draw_versus, "list_item": draw_list_item, "stars": draw_stars,
        "quiz_q": draw_quiz_q, "quiz_a": draw_quiz_a, "outro": draw_outro}


# ---------------------------------------------------------------- timeline + render
def build_timeline(script: dict, voice: str, speed: float):
    t = 0.0
    timeline, voice_events, sfx_events = [], [], []
    for i, sc in enumerate(script["scenes"]):
        sc = dict(sc)
        audio, words = A.tts(sc["say"], voice=voice, speed=speed) if sc.get("say") else (None, [])
        speech = len(audio) / A.SR if audio is not None else 0
        lead = 0.12 if i else 0.0  # hook speaks immediately: no dead air
        dur = max(MIN_DUR.get(sc["type"], 1.2), speech + lead + 0.22)
        if sc["type"] == "quiz_q":
            sc["_countdown_start"] = speech + lead + 0.15
            dur = sc["_countdown_start"] + 3.1
            for k in range(3):
                sfx_events.append((t + sc["_countdown_start"] + k, "tick"))
        if audio is not None:
            voice_events.append((t + lead, audio))
        for w in words:
            w["start"] += t + lead
            w["end"] += t + lead
        if sc["type"] in SCENE_SFX:
            sfx_events.append((t, SCENE_SFX[sc["type"]]))
        if sc["type"] == "stat":
            sfx_events.append((t + 0.1 + min(1.6, dur * 0.55), "pop"))
        timeline.append({"scene": sc, "start": t, "end": t + dur, "words": words})
        t += dur
    return timeline, voice_events, sfx_events, t


def _footage_audio(rel, total, gain):
    """Game sound from the clip, looped to the video length and kept under the narration."""
    import subprocess
    import numpy as np
    from .backgrounds import FOOTAGE
    try:
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-stream_loop", "-1", "-i", str(FOOTAGE / rel), "-t", str(total + 0.5),
                              "-f", "f32le", "-ac", "1", "-ar", str(A.SR), "pipe:1"], capture_output=True, check=True).stdout
        a = np.frombuffer(pcm, np.float32).copy()
        return a / (np.abs(a).max() + 1e-6) * gain
    except Exception as ex:
        print(f"[render] no footage audio: {ex}")
        return None


def render_animated(script: dict, out_path: str, cfg: dict, background_video: str | None = None,
                    bg_start: float = 0.0, seed: int = 0):
    A.configure(cfg)
    timeline, vev, sev, total = build_timeline(script, None, None)
    words = [w for seg in timeline for w in seg["words"]]
    chunks = caption_chunks(words)
    base = None
    if script.get("footage") and script.get("footage_audio", 0.35):
        base = _footage_audio(script["footage"], total, float(script.get("footage_audio", 0.35)))
    mixed = A.mix(total, vev, sev, music_seed=seed,
                  music_gain=cfg.get("music_gain", 0.32) * (0.5 if base is not None else 1.0), base_audio=base)
    tmp = Path(tempfile.mkdtemp())
    wav = str(tmp / "mix.wav")
    A.write_wav(wav, mixed)
    # one shared stickman world per video so characters carry across scenes
    shared = {}
    for i, seg in enumerate(timeline):
        if seg["scene"]["type"] == "stick":
            seg["scene"]["_world_ref"] = shared
            seg["scene"]["_key"] = i
    all_stick = all(seg["scene"]["type"] == "stick" for seg in timeline)
    if all_stick:
        bg = BlankBackground()
    elif background_video:
        bg = VideoBackground(background_video, bg_start)
    else:
        from .backgrounds import SceneBackgrounds
        bg = SceneBackgrounds(script, timeline, seed, cfg)
    enc = Encoder(out_path, wav)
    kicker_pill = D.pill(script.get("kicker", "GTA 6"), 34)
    from .moments import draw_captions
    n_frames = int(total * FPS)
    for fi in range(n_frames):
        t = fi / FPS
        frame = bg.frame(t)
        seg = next((s for s in timeline if s["start"] <= t < s["end"]), timeline[-1])
        lt, d = t - seg["start"], seg["end"] - seg["start"]
        if not all_stick:
            frame.paste(D.scrim(), (0, 0), D.scrim())
        DRAW[seg["scene"]["type"]](frame, seg["scene"], lt, d)
        si = timeline.index(seg)
        D.progress_segments(frame, len(timeline), si, lt / d)
        paste(frame, kicker_pill, W / 2, 190, 1)
        draw_captions(frame, chunks, t, y=1505 if all_stick else D.CAPTION_Y)
        if lt < 0.1 and not all_stick:  # flash cut between scenes
            frame = Image.blend(frame, Image.new("RGB", (W, H), WHITE), 0.35 * (1 - lt / 0.1))
        enc.write(frame)
    enc.close()
    return {"duration": total, "path": out_path}
