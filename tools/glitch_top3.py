"""One-off builder: "Top 3 craziest GTA 6 glitches" from three creator-permitted clips.

Layout (1080x1920): blurred fill background, the clip cropped to 1080x1020 in the middle, rank banner on top,
big word-by-word captions underneath, bouncing arrows that follow the glitch in each clip.
Usage: python tools/glitch_top3.py <topless.mp4> <flying_car.mp4> <first_person.mp4> <out.mp4>
"""
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import audio as A  # noqa: E402
from pipeline.render import lit_stage  # noqa: E402

W, H, FPS = 1080, 1920, 30
VY, VH = 430, 1020                     # video band
CROP = 1080 / (VH * 16 / 9)            # fraction of source width that fits the band
ANTON = str(ROOT / "assets/fonts/Anton-Regular.ttf")
YEL, PINK = (255, 214, 10), (255, 70, 160)

# rank, label, source, [(in, out), ...], crop centre, arrow keys {src_t: (u, v)}, arrow window (src), narration
SEGMENTS = [
    dict(rank=3, label="LUCIA LOST HER SHIRT", src=0, cuts=[(0.0, 3.8), (5.0, 9.6)], cx=0.40,
         arrow={0: (.24, .56), 1: (.38, .55), 2: (.45, .50), 3: (.45, .43), 3.8: (.45, .45), 5: (.45, .48),
                6: (.45, .48), 7: (.45, .55), 8: (.45, .55), 9: (.45, .55), 9.6: (.45, .55)},
         show=(1.9, 9.6),
         say="Top three craziest GTA 6 glitches. Number three: Lucia's shirt vanished, and she kept running like nothing happened."),
    dict(rank=2, label="THE TRUCK THAT FLIES", src=1, cuts=[(9.0, 17.0)], cx=0.50,
         arrow={9: (.50, .62), 9.5: (.49, .55), 10: (.49, .50), 10.5: (.48, .45), 11: (.47, .36), 11.5: (.52, .40),
                12: (.45, .40), 12.5: (.48, .40), 13: (.48, .42), 13.5: (.48, .42), 14: (.45, .45)},
         show=(10.8, 14.2),
         say="Number two: this truck hit one bump and decided it's an airplane now."),
    dict(rank=1, label="SECRET FIRST PERSON", src=2, cuts=[(0.0, 8.8)], cx=0.47,
         arrow={0: (.47, .80), 3.2: (.47, .80)}, show=(0.3, 3.2),
         say="And number one: a glitch that drops you into first person, hands on the wheel. Which one's the craziest?"),
]


def font(sz):
    return ImageFont.truetype(ANTON, sz)


def keyed(keys, t):
    ks = sorted(keys)
    if t <= ks[0]:
        return keys[ks[0]]
    for a, b in zip(ks, ks[1:]):
        if a <= t <= b:
            u = (t - a) / (b - a)
            return tuple(keys[a][i] + (keys[b][i] - keys[a][i]) * u for i in range(2))
    return keys[ks[-1]]


def outlined(d, xy, text, f, fill, stroke=10, anchor="mm"):
    d.text(xy, text, font=f, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0), anchor=anchor)


def arrow_img(scale=1.0):
    """Fat yellow arrow pointing down-left, black outline."""
    s = 220
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = [(20, 200), (40, 105), (68, 133), (170, 30), (192, 52), (90, 155), (118, 183)]   # head at bottom-left
    d.polygon(pts, fill=(0, 0, 0, 255))
    shrink = [(x + (100 - x) * 0.12, y + (110 - y) * 0.12) for x, y in pts]
    d.polygon(shrink, fill=(*YEL, 255))
    return im


def decode(src, t0, t1, cx):
    """Yield (band, bg) RGB frames for a source range."""
    w_src = int(VH * 16 / 9) // 2 * 2
    x0 = int(min(max(cx - CROP / 2, 0), 1 - CROP) * w_src)
    vf = (f"fps={FPS},scale={w_src}:{VH}:flags=lanczos,split[a][b];"
          f"[a]crop=1080:{VH}:{x0}:0[band];[b]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
          f"boxblur=30:3,eq=brightness=-0.18:saturation=1.2[bg];[band][bg]vstack")
    cmd = ["ffmpeg", "-v", "error", "-ss", str(t0), "-to", str(t1), "-i", src, "-filter_complex", vf,
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = 1080 * (VH + 1920) * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        a = np.frombuffer(buf, np.uint8).reshape(VH + 1920, 1080, 3)
        yield Image.fromarray(a[:VH]), Image.fromarray(a[VH:])
    p.wait()


def main(srcs, out):
    cfg = yaml.safe_load(open(ROOT / "config.yaml"))
    A.configure(cfg)
    work = Path(tempfile.mkdtemp())
    # ---- narration + timeline
    timeline, voice_ev, sfx_ev, game = [], [], [], []
    t = 0.0
    for k, seg in enumerate(SEGMENTS):
        dur = sum(b - a for a, b in seg["cuts"])
        wav, words = A.tts(seg["say"])
        vlen = len(wav) / A.SR
        lead = 0.25 if k else 0.15
        if vlen + lead > dur:
            print(f"[warn] narration {vlen:.1f}s longer than clip {dur:.1f}s for #{seg['rank']}")
        voice_ev.append((t + lead, wav))
        seg["words"] = [dict(w, start=w["start"] + t + lead, end=w["end"] + t + lead) for w in words]
        seg["t0"], seg["t1"] = t, t + dur
        if k:
            sfx_ev.append((t - 0.15, "whoosh"))
        timeline.append(seg)
        t += dur
    total = t
    # game audio: the cut ranges, back to back, quiet under the voice
    parts = []
    for seg in SEGMENTS:
        for a, b in seg["cuts"]:
            pth = work / f"g{len(parts)}.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-to", str(b), "-i", srcs[seg["src"]],
                            "-vn", "-ac", "1", "-ar", str(A.SR), str(pth)], check=True)
            parts.append(sf.read(pth, dtype="float32")[0])
    base = np.concatenate(parts)[: int(total * A.SR)] * 0.30
    mix = A.mix(total, voice_ev, sfx_ev, music_seed=7, music_gain=0.12, base_audio=base)
    sf.write(work / "mix.wav", mix, A.SR)

    # ---- video
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-i", str(work / "mix.wav"), "-c:v", "libx264", "-preset",
                            "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                            "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    arrow = arrow_img()
    fi = 0
    for seg in timeline:
        for a, b in seg["cuts"]:
            for band, bg in decode(srcs[seg["src"]], a, b, seg["cx"]):
                tt = fi / FPS
                src_t = a + (tt - seg["t0"] - sum(bb - aa for aa, bb in seg["cuts"][: seg["cuts"].index((a, b))]))
                frame = bg.copy()
                frame.paste(band, (0, VY))
                d = ImageDraw.Draw(frame)
                # thin pink frame lines around the video band
                d.rectangle([0, VY - 6, W, VY], fill=PINK)
                d.rectangle([0, VY + VH, W, VY + VH + 6], fill=PINK)
                # progress timeline (3 segments, disco pink)
                for i, s2 in enumerate(timeline):
                    x0, x1 = 40 + i * 340, 40 + i * 340 + 320
                    d.rounded_rectangle([x0, 46, x1, 58], 6, fill=(90, 70, 100))
                    p = min(1, max(0, (tt - s2["t0"]) / (s2["t1"] - s2["t0"])))
                    if p > 0:
                        d.rounded_rectangle([x0, 46, x0 + max(12, int(320 * p)), 58], 6, fill=PINK)
                intro = tt < 1.9
                # rank banner
                if not intro:
                    pop = min(1, (tt - max(seg["t0"], 1.9)) / 0.18)
                    f_rank = font(int(150 * (0.7 + 0.3 * pop)))
                    outlined(d, (W // 2, 205), f"#{seg['rank']}", f_rank, YEL, 12)
                    outlined(d, (W // 2, 340), seg["label"], font(70), (255, 255, 255), 8)
                # arrow
                s0, s1 = seg["show"]
                if s0 <= src_t <= s1:
                    u, v = keyed(seg["arrow"], src_t)
                    x = (u - (min(max(seg["cx"] - CROP / 2, 0), 1 - CROP))) / CROP * W
                    y = VY + v * VH
                    bob = 16 * (1 + math.sin(tt * 9)) / 2
                    k = min(1, (src_t - s0) / 0.15)
                    sz = max(1, int(220 * k))
                    ar = arrow.resize((sz, sz))
                    tipx, tipy = 20 * sz / 220, 200 * sz / 220          # arrow tip inside the image
                    frame.paste(ar, (int(x - tipx + 6 + bob), int(y - tipy - 6 - bob)), ar)
                # captions (2-3 words, current word yellow)
                words = [w for w in seg["words"] if w["start"] - 0.05 <= tt]
                if words and tt <= seg["words"][-1]["end"] + 0.4:
                    cur = len(words) - 1
                    g0 = cur - cur % 3
                    grp = seg["words"][g0:g0 + 3]
                    f_cap = font(96)
                    txt = [w["w"].upper().strip() for w in grp]
                    widths = [d.textlength(x + " ", font=f_cap) for x in txt]
                    xx = W / 2 - sum(widths) / 2
                    for i, (x, wd) in enumerate(zip(txt, widths)):
                        col = YEL if g0 + i == cur else (255, 255, 255)
                        outlined(d, (xx, VY + VH + 190), x, f_cap, col, 9, anchor="lm")
                        xx += wd
                # intro title over the first glitch, then it flies away
                if tt < 2.3:
                    k = 1 if tt < 1.7 else 1 - (tt - 1.7) / 0.6
                    yoff = (1 - k) * -500
                    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    od = ImageDraw.Draw(ov)
                    sc = min(1, 0.6 + tt * 2.5)
                    outlined(od, (W // 2, VY + 300 + yoff), "TOP 3", font(int(230 * sc)), YEL, 14)
                    outlined(od, (W // 2, VY + 520 + yoff), "CRAZIEST", font(int(130 * sc)), (255, 255, 255), 10)
                    outlined(od, (W // 2, VY + 670 + yoff), "GTA 6 GLITCHES", font(int(110 * sc)), PINK, 10)
                    frame = Image.alpha_composite(frame.convert("RGBA"), ov).convert("RGB")
                enc.stdin.write(frame.tobytes())
                fi += 1
    enc.stdin.close()
    enc.wait()
    print(f"[done] {out} {fi / FPS:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1:4], sys.argv[4])
