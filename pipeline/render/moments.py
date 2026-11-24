"""Polished layout for streamer-moment videos (Top 5 countdowns and single clips).

1080x1920 frame, top to bottom:
  - story-style progress segments (one per moment)
  - header pill:  TOP 5 · STREAMER
  - moment card:  gradient rank badge (#5) + the moment's title, auto-fitted to the space beside it
  - the clip, cropped to 4:3 so it's big, with rounded corners and a credit chip
  - captions under the clip
Over a blurred, darkened copy of the clip. Every element has its own zone, so nothing overlaps.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .. import audio as A
from .core import (BLACK, FPS, H, W, WHITE, YELLOW, Encoder, caption_chunks, ease_out_back, ease_out_cubic,
                   font, paste, text_sprite)

ACCENT1, ACCENT2 = (255, 46, 120), (255, 150, 40)   # pink -> orange
TWITCH = (145, 70, 255)
CLIP_W, CLIP_H, CLIP_Y = 1040, 585, 610              # full 16:9 so facecams are never cut off
CAP_Y = 1330


def clean_title(t: str, max_chars=52) -> str:
    t = re.sub(r"[^\x20-\x7E]", "", t or "")          # drop emoji the font can't draw
    t = re.sub(r"\s+", " ", t).strip(" -|:")
    if len(t) > max_chars:
        t = t[:max_chars].rsplit(" ", 1)[0] + "..."
    return t.upper() or "UNREAL MOMENT"


def _gradient(w, h, c1, c2, horizontal=True):
    x = np.linspace(0, 1, w if horizontal else h)
    g = (np.array(c1)[None, :] * (1 - x[:, None]) + np.array(c2)[None, :] * x[:, None]).astype(np.uint8)
    arr = np.broadcast_to(g[None, :, :], (h, w, 3)) if horizontal else np.broadcast_to(g[:, None, :], (h, w, 3))
    return Image.fromarray(np.ascontiguousarray(arr))


def _round_mask(w, h, r):
    m = Image.new("L", (w * 2, h * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * 2 - 1, h * 2 - 1), r * 2, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def fit_text(text, box_w, max_lines, sizes=(68, 62, 56, 50, 46, 42), kind="black"):
    """Largest size where the text wraps into <= max_lines within box_w."""
    from .core import wrap
    for s in sizes:
        f = font(kind, s)
        lines = wrap(text, f, box_w)
        if len(lines) <= max_lines and max(f.getlength(l) for l in lines) <= box_w:
            return s, lines
    f = font(kind, sizes[-1])
    lines = wrap(text, f, box_w)[:max_lines]
    return sizes[-1], lines


class Layout:
    """Pre-rendered static pieces for one moment."""

    def __init__(self, rank, total, title, streamer, credit):
        self.rank, self.total = rank, total
        # header pill
        hp = f"TOP {total}  •  {streamer.upper()}" if rank else streamer.upper()
        ht = text_sprite(hp, "black", 34, WHITE, 0, BLACK, 900, False)
        self.header = Image.new("RGBA", (ht.width + 56, ht.height + 18), (0, 0, 0, 0))
        ImageDraw.Draw(self.header).rounded_rectangle((0, 0, self.header.width - 1, self.header.height - 1),
                                                      self.header.height // 2, fill=(0, 0, 0, 165))
        ImageDraw.Draw(self.header).ellipse((18, self.header.height // 2 - 7, 32, self.header.height // 2 + 7), fill=ACCENT1)
        self.header.alpha_composite(ht, (40, 9))
        # moment card: badge + title
        card_w, card_h = 1000, 250
        badge = 196 if rank else 0
        text_w = card_w - badge - 90 if rank else card_w - 80
        size, lines = fit_text(title, text_w, 3)
        f = font("black", size)
        asc, desc = f.getmetrics()
        lh = int((asc + desc) * 1.02)
        card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle((0, 0, card_w - 1, card_h - 1), 34, fill=(10, 10, 18, 200))
        grad = _gradient(card_w, 8, ACCENT1, ACCENT2)
        card.paste(grad, (0, card_h - 8), _round_mask(card_w, 8, 4))
        tx = badge + 60 if rank else 40
        ty = (card_h - lh * len(lines)) // 2 - 4
        for i, ln in enumerate(lines):
            d.text((tx + 3, ty + i * lh + 4), ln, font=f, fill=(0, 0, 0, 160))
            d.text((tx, ty + i * lh), ln, font=f, fill=WHITE)
        self.card = card
        # rank badge (animated separately)
        self.badge = None
        if rank:
            b = 196
            g = _gradient(b, b, ACCENT1, ACCENT2).convert("RGBA")
            g.putalpha(_round_mask(b, b, 48))
            num = text_sprite(f"#{rank}", "display", 120, WHITE, 0, BLACK, 300, True, 0.0)
            g.alpha_composite(num, ((b - num.width) // 2, (b - num.height) // 2 + 4))
            self.badge = g
        # credit chip
        ct = text_sprite(credit, "bold", 30, WHITE, 0, BLACK, 700, False)
        chip = Image.new("RGBA", (ct.width + 70, ct.height + 16), (0, 0, 0, 0))
        cd = ImageDraw.Draw(chip)
        cd.rounded_rectangle((0, 0, chip.width - 1, chip.height - 1), chip.height // 2, fill=(0, 0, 0, 175))
        cd.rounded_rectangle((16, chip.height // 2 - 11, 38, chip.height // 2 + 11), 5, fill=TWITCH)
        chip.alpha_composite(ct, (50, 8))
        self.chip = chip
        self.clip_mask = _round_mask(CLIP_W, CLIP_H, 36)
        border = Image.new("RGBA", (CLIP_W + 12, CLIP_H + 12), (0, 0, 0, 0))
        ImageDraw.Draw(border).rounded_rectangle((0, 0, CLIP_W + 11, CLIP_H + 11), 42, fill=(255, 255, 255, 235))
        self.border = border

    def draw(self, frame, clip_img, t, seg_progress, seg_index):
        # progress segments (story style)
        d = ImageDraw.Draw(frame)
        n = max(1, self.total) if self.rank else 1
        gap, x0, x1, y = 10, 40, W - 40, 112
        sw = (x1 - x0 - gap * (n - 1)) / n
        for i in range(n):
            xa = x0 + i * (sw + gap)
            d.rounded_rectangle((xa, y, xa + sw, y + 8), 4, fill=(90, 90, 100))
            fill = 1.0 if i < seg_index else (seg_progress if i == seg_index else 0)
            if fill > 0:
                d.rounded_rectangle((xa, y, xa + sw * fill, y + 8), 4, fill=WHITE)
        k = ease_out_cubic(t / 0.35)
        paste(frame, self.header, W / 2, 190, 1, alpha=min(1, t / 0.2))
        # card slides up + fades in
        cx, cy = W / 2, 400 + 40 * (1 - k)
        paste(frame, self.card, cx, cy, 1, alpha=k)
        if self.badge is not None:
            s = ease_out_back(min(1, max(0, (t - 0.05) / 0.4)))
            paste(frame, self.badge, 40 + 98 + 10, 400, 0.4 + 0.6 * s, rot=-8 * (1 - s))
        # clip with border + rounded corners, small zoom-in
        z = 0.94 + 0.06 * ease_out_cubic(t / 0.4)
        bx = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        border = self.border if z > 0.999 else self.border.resize((int(self.border.width * z), int(self.border.height * z)))
        clip = clip_img if z > 0.999 else clip_img.resize((int(CLIP_W * z), int(CLIP_H * z)), Image.BILINEAR)
        mask = self.clip_mask if z > 0.999 else self.clip_mask.resize(clip.size, Image.BILINEAR)
        ccx, ccy = W // 2, CLIP_Y + CLIP_H // 2
        frame.paste(border.convert("RGB"), (ccx - border.width // 2, ccy - border.height // 2), border)
        frame.paste(clip, (ccx - clip.width // 2, ccy - clip.height // 2), mask)
        paste(frame, self.chip, 60 + self.chip.width / 2, CLIP_Y + CLIP_H - 50, 1, alpha=min(1, t / 0.3))
        if t < 0.08:
            frame.paste(Image.blend(frame, Image.new("RGB", frame.size, WHITE), 0.5 * (1 - t / 0.08)))


def draw_captions(frame, chunks, t):
    for ch in chunks:
        if ch[0]["start"] - 0.05 <= t < ch[-1]["end"] + 0.15:
            active = next((w["w"] for w in ch if w["start"] <= t < w["end"] + 0.05), "")
            text = clean_title(" ".join(w["w"] for w in ch), 40)
            spr = text_sprite(text, "black", 68, WHITE, 8, BLACK, 940, True, 0.0,
                              highlight=(clean_title(active, 40),) if active else (), hl_fill=YELLOW)
            paste(frame, spr, W / 2, CAP_Y, 0.9 + 0.1 * ease_out_back((t - ch[0]["start"]) / 0.15))
            return


def _decode(path, start, dur, vf):
    return subprocess.Popen(["ffmpeg", "-v", "quiet", "-ss", str(start), "-t", str(dur), "-i", path, "-an",
                             "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)


def _clip_audio(path, start, dur):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", path, "-vn",
                          "-f", "f32le", "-ac", "1", "-ar", str(A.SR), "pipe:1"], capture_output=True).stdout
    return np.frombuffer(pcm, np.float32).copy()


def render_moment(video_path, out_path, *, title, streamer, credit, rank=None, total=5,
                  words=None, start=0.0, max_len=None, seg_index=0):
    full = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "default=nw=1:nk=1", video_path]))
    dur = min(full - start, max_len) if max_len else full - start
    if words:
        words = [{**w, "start": w["start"] - start, "end": w["end"] - start} for w in words
                 if start <= w["start"] < start + dur]
    chunks = caption_chunks(words or [], max_words=3)
    lay = Layout(rank, total, clean_title(title), streamer, credit)
    # audio: clip sound + a whoosh on the cut
    clip_a = _clip_audio(video_path, start, dur)
    aud = A.mix(dur, [(0, clip_a)], [(0, "whoosh")], music_gain=0)
    tmp = Path(tempfile.mkdtemp())
    wav = str(tmp / "a.wav")
    A.write_wav(wav, aud)
    fg = _decode(video_path, start, dur, f"fps={FPS},scale={CLIP_W}:{CLIP_H}:force_original_aspect_ratio=increase:flags=lanczos,"
                                         f"crop={CLIP_W}:{CLIP_H}")
    bw, bh = 216, 384
    bg = _decode(video_path, start, dur, f"fps={FPS},scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
                                         f"boxblur=8:2,eq=brightness=-0.28:saturation=1.25")
    enc = Encoder(out_path, wav)
    n = int(dur * FPS)
    for fi in range(n):
        fb = fg.stdout.read(CLIP_W * CLIP_H * 3)
        bb = bg.stdout.read(bw * bh * 3)
        if len(fb) < CLIP_W * CLIP_H * 3 or len(bb) < bw * bh * 3:
            break
        t = fi / FPS
        frame = Image.fromarray(np.frombuffer(bb, np.uint8).reshape(bh, bw, 3)).resize((W, H), Image.BICUBIC)
        clip = Image.fromarray(np.frombuffer(fb, np.uint8).reshape(CLIP_H, CLIP_W, 3))
        lay.draw(frame, clip, t, t / dur, seg_index)
        draw_captions(frame, chunks, t)
        enc.write(frame)
    for p in (fg, bg):
        p.kill()
    enc.close()
    return {"duration": dur, "path": out_path}


def render_card(video_path, out_path, *, big, small, pill, say, total=5, seg_index=0, outro=False):
    """Intro/outro card over the blurred clip, with the narrator voice."""
    A.configure({})
    voice, words = A.tts(say)
    dur = max(2.0, len(voice) / A.SR + 0.35)
    aud = A.mix(dur, [(0.1, voice)], [(0, "boom" if not outro else "pop")], music_gain=0.25, music_seed=3)
    tmp = Path(tempfile.mkdtemp())
    wav = str(tmp / "a.wav")
    A.write_wav(wav, aud)
    bw, bh = 216, 384
    bg = _decode(video_path, 0, dur + 0.2, f"fps={FPS},scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
                                           f"boxblur=10:2,eq=brightness=-0.35:saturation=1.3")
    big_spr = text_sprite(big, "display", 220, WHITE, 0, BLACK, 980, True, -0.08)
    small_spr = text_sprite(small, "black", 60, WHITE, 0, BLACK, 940, True)
    pt = text_sprite(pill, "black", 58, WHITE, 0, BLACK, 900, False)
    pill_img = _gradient(pt.width + 80, pt.height + 30, ACCENT1, ACCENT2).convert("RGBA")
    pill_img.putalpha(_round_mask(pill_img.width, pill_img.height, pill_img.height // 2))
    pill_img.alpha_composite(pt, (40, 15))
    enc = Encoder(out_path, wav)
    last = Image.new("RGB", (W, H), (10, 10, 18))
    for fi in range(int(dur * FPS)):
        t = fi / FPS
        bb = bg.stdout.read(bw * bh * 3)
        if len(bb) == bw * bh * 3:
            last = Image.fromarray(np.frombuffer(bb, np.uint8).reshape(bh, bw, 3)).resize((W, H), Image.BICUBIC)
        frame = last.copy()
        s = ease_out_back(min(1, t / 0.4))
        paste(frame, big_spr, W / 2, 760, 0.5 + 0.5 * s)
        paste(frame, pill_img, W / 2, 1010, ease_out_back(min(1, max(0, (t - 0.15) / 0.35))))
        paste(frame, small_spr, W / 2, 1150, 1, alpha=min(1, max(0, (t - 0.3) / 0.3)))
        enc.write(frame)
    bg.kill()
    enc.close()
    return {"duration": dur, "path": out_path}
