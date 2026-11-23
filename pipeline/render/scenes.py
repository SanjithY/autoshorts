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


# ---------------------------------------------------------------- scene drawers
def _kicker(frame, label, t):
    spr = text_sprite(label.upper(), "black", 40, BLACK, 0, BLACK, 900, False)
    box = rounded_box(spr.width + 40, spr.height + 6, YELLOW, 18)
    box.paste(spr, (20, 3), spr)
    paste(frame, box, W / 2, 245, 1 + 0.03 * math.sin(t * 4))


def draw_hook(f, s, lt, d):
    p = ease_out_back(lt / 0.28)
    shake = (math.sin(lt * 60) * 10 * max(0, 1 - lt / 0.3))
    spr = text_sprite(s["text"].upper(), "display", 175, WHITE, 12, BLACK, 940, True, 0.0,
                      tuple(s.get("highlight", [])), YELLOW)
    paste(f, spr, W / 2 + shake, CENTER_Y, 0.5 + 0.5 * p, rot=-3 * (1 - ease_out_cubic(lt / 0.4)) + 2)


def draw_text(f, s, lt, d):
    p = ease_out_back(lt / 0.3)
    spr = text_sprite(s["text"].upper(), "display", 130, WHITE, 10, BLACK, 920, True, 0.02,
                      tuple(s.get("highlight", [])), YELLOW)
    paste(f, spr, W / 2, CENTER_Y - 40 + 40 * (1 - p), 0.7 + 0.3 * p, alpha=min(1, lt / 0.12))
    if s.get("sub"):
        sub = text_sprite(s["sub"], "bold", 54, TEAL, 6, BLACK, 880)
        paste(f, sub, W / 2, CENTER_Y + spr.height / 2 + 50, 1, alpha=prog(lt, 0.35, 0.25))


def _fmt(v, s):
    dec = int(s.get("decimals", 0))
    num = f"{v:,.{dec}f}"
    return f"{s.get('prefix', '')}{num}{s.get('suffix', '')}"


def draw_stat(f, s, lt, d):
    lab = text_sprite(s.get("label", "").upper(), "black", 60, TEAL, 7, BLACK, 900)
    paste(f, lab, W / 2, CENTER_Y - 230, 1, alpha=prog(lt, 0, 0.2))
    cnt = ease_out_cubic(prog(lt, 0.1, min(1.6, d * 0.55)))
    val = float(s["value"]) * cnt
    done = cnt >= 0.999
    spr = text_sprite(_fmt(val if not done else float(s["value"]), s), "display", 230,
                      YELLOW if done else WHITE, 13, BLACK, 1000)
    pulse = 1 + (0.12 * math.exp(-(lt - 0.1 - min(1.6, d * 0.55)) * 8) if done else 0)
    paste(f, spr, W / 2, CENTER_Y, pulse)
    if s.get("sub"):
        sub = text_sprite(s["sub"], "bold", 52, WHITE, 6, BLACK, 880)
        paste(f, sub, W / 2, CENTER_Y + 220, 1, alpha=prog(lt, 0.9, 0.3))


def draw_bars(f, s, lt, d):
    items = s["items"][:4]
    title = text_sprite(s.get("title", "").upper(), "black", 62, WHITE, 7, BLACK, 900)
    paste(f, title, W / 2, 400, 1, alpha=prog(lt, 0, 0.2))
    mx = max(float(i["value"]) for i in items) or 1
    hi = s.get("highlight", 0)
    dr = ImageDraw.Draw(f)
    for k, it in enumerate(items):
        y = 540 + k * 190
        g = ease_out_cubic(prog(lt, 0.25 + k * 0.35, 0.7))
        lab = text_sprite(it["label"].upper(), "black", 46, WHITE, 6, BLACK, 800)
        paste(f, lab, 90 + lab.width / 2, y, 1, alpha=prog(lt, 0.2 + k * 0.35, 0.2))
        bw = int(820 * float(it["value"]) / mx * g)
        col = YELLOW if k == hi else PINK
        if bw > 4:
            dr.rounded_rectangle((90, y + 40, 90 + bw, y + 115), 16, fill=col, outline=BLACK, width=5)
        if g > 0.6:
            vs = text_sprite(it.get("display", str(it["value"])), "display", 64, WHITE, 7, BLACK, 600)
            x = 90 + bw + 20 + vs.width / 2
            if x + vs.width / 2 > W - 30:  # no room after the bar: put the value inside it
                x = 90 + bw - vs.width / 2 - 14
            paste(f, vs, x, y + 78, 1)


def draw_versus(f, s, lt, d):
    l, r = s.get("left", "A"), s.get("right", "B")
    p = ease_out_back(lt / 0.35)
    ls = text_sprite(l.upper(), "display", 110, PINK, 10, BLACK, 450)
    rs = text_sprite(r.upper(), "display", 110, TEAL, 10, BLACK, 450)
    paste(f, ls, 270 - 400 * (1 - p), 400, 1)
    paste(f, rs, 810 + 400 * (1 - p), 400, 1)
    vs = text_sprite("VS", "display", 90, YELLOW, 9, BLACK, 300)
    paste(f, vs, W / 2, 400, ease_out_back(prog(lt, 0.2, 0.3)))
    rows = s.get("rows", [])[:4]
    for k, row in enumerate(rows):
        a = prog(lt, 0.5 + k * 0.45, 0.25)
        if a <= 0:
            continue
        y = 590 + k * 165
        box = rounded_box(980, 140, (0, 0, 0, 150), 26)
        paste(f, box, W / 2, y, 0.9 + 0.1 * ease_out_back(a), a)
        lab = text_sprite(row["label"].upper(), "bold", 34, WHITE, 0, BLACK, 360, False)
        paste(f, lab, W / 2, y, 1, a)
        lv = text_sprite(str(row["l"]), "display", 62, PINK, 6, BLACK, 300)
        rv = text_sprite(str(row["r"]), "display", 62, TEAL, 6, BLACK, 300)
        paste(f, lv, 200, y, 1, a)
        paste(f, rv, 880, y, 1, a)


def draw_list_item(f, s, lt, d):
    p = ease_out_back(lt / 0.3)
    num = text_sprite(f"#{s['n']}", "display", 300, YELLOW, 14, BLACK, 600)
    paste(f, num, W / 2 - 600 * (1 - p), CENTER_Y - 200, 1, rot=6 * (1 - p))
    spr = text_sprite(s["text"].upper(), "display", 112, WHITE, 10, BLACK, 920, True, 0.02,
                      tuple(s.get("highlight", [])), YELLOW)
    q = ease_out_back(prog(lt, 0.15, 0.3))
    paste(f, spr, W / 2, CENTER_Y + 110, 0.6 + 0.4 * q, alpha=min(1, q * 2))


def draw_stars(f, s, lt, d):
    n = int(s.get("n", 6))
    dr = ImageDraw.Draw(f)
    y = CENTER_Y - 150
    for k in range(6):
        cx = 140 + k * 160
        on = lt > 0.3 + k * 0.28 and k < n
        a = ease_out_back(prog(lt, 0.3 + k * 0.28, 0.2)) if k < n else 1
        r = 62 * (a if on else 1)
        flash = on and int(lt * 6) % 2 == 0 and k == n - 1 and lt > 0.3 + n * 0.28
        fill = (WHITE if flash else HOT) if on else (0, 0, 0)
        dr.polygon(star_points(cx, y, r, r * 0.45), fill=fill, outline=WHITE, width=5)
    spr = text_sprite(s["text"].upper(), "display", 120, WHITE, 10, BLACK, 920, True, 0.02,
                      tuple(s.get("highlight", [])), YELLOW)
    paste(f, spr, W / 2, CENTER_Y + 120, 1, alpha=prog(lt, 0.2, 0.25))


def _options(f, s, lt, reveal=None):
    opts = s["options"][:3]
    for k, o in enumerate(opts):
        a = prog(lt, 0.3 + k * 0.25, 0.2)
        y = 760 + k * 165
        col = (30, 20, 60, 230)
        if reveal is not None:
            col = (40, 170, 90, 255) if k == reveal else (40, 30, 60, 140)
        box = rounded_box(900, 135, col, 30, WHITE, 5)
        paste(f, box, W / 2, y, 0.9 + 0.1 * ease_out_back(a), a)
        t = text_sprite(f"{'ABC'[k]}) {o}", "black", 52, WHITE, 0, BLACK, 820, False)
        paste(f, t, W / 2, y, 1, a)


def draw_quiz_q(f, s, lt, d):
    q = text_sprite(s["question"].upper(), "display", 96, WHITE, 9, BLACK, 940, True, 0.02,
                    tuple(s.get("highlight", [])), YELLOW)
    paste(f, q, W / 2, 470, ease_out_back(lt / 0.3))
    _options(f, s, lt)
    cd = s.get("_countdown_start")
    if cd is not None and lt >= cd:
        rem = max(0.0, 3 - (lt - cd))
        dr = ImageDraw.Draw(f)
        cx, cy, r = W / 2, 1290, 95
        dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 200))
        dr.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * rem / 3, fill=YELLOW, width=18)
        num = text_sprite(str(math.ceil(rem) if rem > 0 else 0), "display", 110, WHITE, 6, BLACK, 300)
        paste(f, num, cx, cy, 1 + 0.15 * (1 - (rem % 1)))


def draw_quiz_a(f, s, lt, d):
    q = text_sprite(s.get("question", "").upper(), "display", 80, WHITE, 8, BLACK, 940)
    paste(f, q, W / 2, 470, 1)
    _options(f, {**s, "options": s["options"]}, 9, reveal=int(s["answer"]))
    if lt > 0.1:
        ok = text_sprite("CORRECT ANSWER: " + "ABC"[int(s["answer"])], "black", 50, GREEN, 6, BLACK, 900)
        paste(f, ok, W / 2, 660, ease_out_back(prog(lt, 0.1, 0.25)))


def draw_outro(f, s, lt, d):
    spr = text_sprite(s["text"].upper(), "display", 120, WHITE, 10, BLACK, 920, True, 0.02,
                      tuple(s.get("highlight", [])), YELLOW)
    paste(f, spr, W / 2, CENTER_Y - 60, ease_out_back(lt / 0.3))
    cta = s.get("cta")
    if cta:
        c = text_sprite(cta.upper(), "black", 50, BLACK, 0, BLACK, 820, False)
        box = rounded_box(c.width + 60, c.height + 30, PINK, 30)
        box.paste(c, (30, 15), c)
        paste(f, box, W / 2, CENTER_Y + 200, 1 + 0.05 * math.sin(lt * 6), prog(lt, 0.3, 0.2))


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
    kicker = script.get("kicker", "GTA 6")
    n_frames = int(total * FPS)
    for fi in range(n_frames):
        t = fi / FPS
        frame = bg.frame(t)
        seg = next((s for s in timeline if s["start"] <= t < s["end"]), timeline[-1])
        lt, d = t - seg["start"], seg["end"] - seg["start"]
        _kicker(frame, kicker, t)
        DRAW[seg["scene"]["type"]](frame, seg["scene"], lt, d)
        draw_caption(frame, chunks, t, y=1505 if all_stick else CAPTION_Y)
        draw_progress(frame, t, total)
        if lt < 0.1 and not all_stick:  # flash cut between scenes
            frame = Image.blend(frame, Image.new("RGB", (W, H), WHITE), 0.35 * (1 - lt / 0.1))
        enc.write(frame)
    enc.close()
    return {"duration": total, "path": out_path}
