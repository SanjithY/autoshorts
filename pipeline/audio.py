"""Free audio: Edge neural voice (with Kokoro local fallback), synthesized music bed and sound effects."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly, lfilter

SR = 44100
ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.environ.get("KOKORO_DIR", ROOT / "models"))


@lru_cache(maxsize=1)
def _kokoro():
    from kokoro_onnx import Kokoro
    return Kokoro(str(MODEL_DIR / "kokoro.onnx"), str(MODEL_DIR / "voices.bin"))


def speak_text_prep(text: str) -> str:
    """Make names/numbers read naturally. Keep "GTA" as one token: both voices spell it G-T-A
    correctly, while "G T A" makes the A sound like the word "a"."""
    t = re.sub(r"\bGTA\s*VI\b", "GTA 6", text)
    t = re.sub(r"\bGTA\s*IV\b", "GTA 4", t)
    t = re.sub(r"\bGTA\s*V\b", "GTA 5", t)
    t = re.sub(r"\bG\s+T\s+A\b", "GTA", t)
    t = re.sub(r"\$(\d+(?:\.\d+)?)\s*B\b", r"\1 billion dollars", t)
    t = re.sub(r"\$(\d+(?:\.\d+)?)\s*M\b", r"\1 million dollars", t)
    t = re.sub(r"\$(\d+(?:\.\d+)?)\s*K\b", r"\1 thousand dollars", t)
    t = t.replace("&", " and ").replace(" vs ", " versus ").replace(" vs. ", " versus ")
    return t


def _trim(samples, sr):
    nz = np.where(np.abs(samples) > 0.01)[0]
    if len(nz):
        samples = samples[max(0, nz[0] - int(0.02 * sr)): nz[-1] + int(0.05 * sr)]
    return samples


def _even_timings(text, dur):
    words = text.split()
    weights = np.array([len(re.sub(r"[^\w$%]", "", w)) + 2 for w in words], float)
    edges = np.concatenate([[0], np.cumsum(weights) / weights.sum()]) * dur
    return [{"w": w, "start": float(edges[i]), "end": float(edges[i + 1])} for i, w in enumerate(words)]


def _edge_tts(text: str, voice: str, rate: str):
    """Microsoft Edge neural voice (free, no key, very natural) + exact word timings."""
    import asyncio
    import subprocess
    import edge_tts

    async def run():
        com = edge_tts.Communicate(speak_text_prep(text), voice, rate=rate, boundary="WordBoundary")
        audio, marks = bytearray(), []
        async for ch in com.stream():
            if ch["type"] == "audio":
                audio.extend(ch["data"])
            elif ch["type"] == "WordBoundary":
                marks.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]))
        return bytes(audio), marks

    mp3, marks = asyncio.run(run())
    if not mp3:
        raise RuntimeError("edge-tts returned no audio")
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(SR), "pipe:1"],
                         input=mp3, capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, np.float32).copy()
    lead = 0.0
    nz = np.where(np.abs(audio) > 0.01)[0]
    if len(nz):
        lead = max(0, nz[0] - int(0.02 * SR)) / SR
        audio = audio[int(lead * SR): nz[-1] + int(0.05 * SR)]
    # map the spoken words back onto the original (display) words for captions
    disp = text.split()
    if marks and len(marks) == len(disp):
        timed = [{"w": disp[i], "start": max(0.0, a - lead), "end": max(0.0, b - lead)} for i, (a, b, _) in enumerate(marks)]
    elif marks:
        timed = [{"w": w, "start": max(0.0, a - lead), "end": max(0.0, b - lead)} for a, b, w in marks]
    else:
        timed = _even_timings(text, len(audio) / SR)
    return audio, timed


def _kokoro_tts(text: str, voice: str, speed: float):
    samples, sr = _kokoro().create(speak_text_prep(text), voice=voice, speed=speed, lang="en-us")
    samples = _trim(np.asarray(samples, np.float32), sr)
    audio = resample_poly(samples, SR, sr).astype(np.float32)
    return audio, _even_timings(text, len(audio) / SR)


TTS_CFG = {"engine": "edge", "edge_voice": "en-US-AndrewMultilingualNeural", "edge_rate": "+8%",
           "voice": "am_michael", "voice_speed": 1.05}


def configure(cfg: dict):
    for k in TTS_CFG:
        if k in cfg:
            TTS_CFG[k] = cfg[k]


_EDGE_FAILS = [0]


def tts(text: str, voice=None, speed=None):
    """Returns (audio float32 @ SR, word timings list[{w,start,end}] relative to clip start)."""
    if TTS_CFG.get("engine", "edge") == "edge" and _EDGE_FAILS[0] < 3:
        import time as _t
        for attempt in range(3):  # the free endpoint hiccups now and then; retry before giving up
            try:
                out = _edge_tts(text, TTS_CFG["edge_voice"], TTS_CFG["edge_rate"])
                _EDGE_FAILS[0] = 0
                return out
            except Exception as ex:
                err = ex
                _t.sleep(2 + 3 * attempt)
        _EDGE_FAILS[0] += 1
        print(f"[tts] edge voice failed 3x ({type(err).__name__}: {str(err)[:100]}); using Kokoro for this line")
    return _kokoro_tts(text, voice or TTS_CFG["voice"], float(speed or TTS_CFG["voice_speed"]))


# ---------------------------------------------------------------- synthesis helpers
def _env(n, a=0.005, d=0.2):
    t = np.arange(n) / SR
    return np.minimum(1, t / a) * np.exp(-t / d)


def _lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    return lfilter([1 - a], [1, -a], x)


def _saw(freq, n, phase=0.0):
    t = np.arange(n) / SR
    return 2 * ((t * freq + phase) % 1) - 1


def note(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def _add(buf, start, x, gain=1.0):
    """Add x into buf at start, clipping at the end of the buffer."""
    if start >= len(buf):
        return
    n = min(len(x), len(buf) - start)
    buf[start:start + n] += (gain * x[:n]).astype(np.float32)


def music_bed(duration: float, seed: int = 0, bpm=None):
    rng = np.random.default_rng(seed)
    bpm = bpm or int(rng.choice([96, 100, 104, 110]))
    root = int(rng.choice([45, 43, 41, 40]))  # A1, G1, F1, E1
    prog = [[0, 3, 7], [-4, 0, 3], [-2, 2, 5], [-5, -2, 2]]  # i - VI - VII - v (minor)
    if rng.random() < 0.5:
        prog = [[0, 3, 7], [5, 8, 12], [-4, 0, 3], [-2, 2, 5]]
    n = int(duration * SR) + SR
    out = np.zeros(n, np.float32)
    beat = 60 / bpm
    step = beat / 4
    bar = beat * 4
    t = 0.0
    i = 0
    while t < duration + 1:
        chord = prog[int(t // bar) % len(prog)]
        s = int(t * SR)
        L = int(step * SR)
        if s + L >= n:
            break
        # bass: 16th-note pulse on chord root/fifth
        b = root + chord[0] + (12 if i % 8 == 6 else 0)
        seg = _saw(note(b), L) * _env(L, 0.003, step * 0.9)
        _add(out, s, _lowpass(seg, 500), 0.22)
        # kick on beats
        if i % 4 == 0:
            kl = int(0.35 * SR)
            kt = np.arange(kl) / SR
            f = 45 + 80 * np.exp(-kt * 30)
            kick = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-kt * 9)
            _add(out, s, kick, 0.5)
        # snare/clap on 2 and 4
        if i % 16 in (4, 12):
            cl = int(0.18 * SR)
            clap = rng.standard_normal(cl) * np.exp(-np.arange(cl) / SR * 25)
            clap = clap - _lowpass(clap, 1500)
            _add(out, s, clap, 0.18)
        # hats on offbeats
        if i % 2 == 1:
            hl = int(0.04 * SR)
            hat = rng.standard_normal(hl) * np.exp(-np.arange(hl) / SR * 120)
            _add(out, s, hat - _lowpass(hat, 6000), 0.05)
        # pad + arp on each beat
        if i % 4 == 0:
            for k, iv in enumerate(chord):
                m = root + 24 + iv
                arp_s = s + int(k * step * SR * 0.0)
                pl = int(beat * SR)
                pad = (_saw(note(m), pl) + _saw(note(m) * 1.004, pl)) * 0.5
                pad = _lowpass(pad, 1800) * np.minimum(1, np.arange(pl) / (0.05 * SR))
                _add(out, arp_s, pad, 0.035)
        if i % 2 == 0:
            m = root + 36 + chord[(i // 2) % 3]
            al = int(step * SR * 1.5)
            arp = np.sin(2 * np.pi * note(m) * np.arange(al) / SR) * _env(al, 0.002, 0.08)
            _add(out, s, arp, 0.05)
        t += step
        i += 1
    out = out[: int(duration * SR)]
    return out / (np.abs(out).max() + 1e-6) * 0.6


def sfx(kind: str, seed=0):
    rng = np.random.default_rng(seed)
    if kind == "whoosh":
        L = int(0.35 * SR)
        x = rng.standard_normal(L)
        cut = np.linspace(400, 6000, L)
        y = np.zeros(L)
        acc = 0.0
        for j in range(L):
            a = np.exp(-2 * np.pi * cut[j] / SR)
            acc = (1 - a) * x[j] + a * acc
            y[j] = acc
        y *= np.sin(np.linspace(0, np.pi, L)) ** 2
        return (0.35 * y / (np.abs(y).max() + 1e-6)).astype(np.float32)
    if kind == "pop":
        L = int(0.12 * SR)
        t = np.arange(L) / SR
        f = 500 + 900 * t / t[-1]
        return (0.4 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 30)).astype(np.float32)
    if kind == "tick":
        L = int(0.05 * SR)
        t = np.arange(L) / SR
        return (0.5 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 90)).astype(np.float32)
    if kind == "ding":
        L = int(0.7 * SR)
        t = np.arange(L) / SR
        y = np.sin(2 * np.pi * 1318 * t) + 0.6 * np.sin(2 * np.pi * 1760 * t)
        return (0.3 * y * np.exp(-t * 5)).astype(np.float32)
    if kind == "boom":
        L = int(0.9 * SR)
        t = np.arange(L) / SR
        f = 30 + 90 * np.exp(-t * 12)
        y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.5)
        return (0.7 * y).astype(np.float32)
    if kind == "siren":
        L = int(0.9 * SR)
        t = np.arange(L) / SR
        f = 900 + 350 * np.sin(2 * np.pi * 2.2 * t)
        y = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t * 2.5)
        return (0.07 * _lowpass(y, 3000)).astype(np.float32)
    raise ValueError(kind)


def mix(duration, voice_events, sfx_events, music_seed=0, music_gain=0.32, base_audio=None):
    """voice_events: [(start_sec, np.array)], sfx_events: [(start_sec, kind)]."""
    n = int(duration * SR) + SR // 10
    voice = np.zeros(n, np.float32)
    for st, a in voice_events:
        s = int(st * SR)
        _add(voice, s, a)
    fx = np.zeros(n, np.float32)
    for k, (st, kind) in enumerate(sfx_events):
        a = sfx(kind, seed=k)
        s = int(st * SR)
        _add(fx, s, a)
    mus = np.zeros(n, np.float32)
    if music_gain > 0:
        m = music_bed(duration + 0.1, seed=music_seed)
        mus[: len(m)] = m[:n]
        # sidechain duck under voice
        env = _lowpass(np.abs(voice), 8)
        env = env / (env.max() + 1e-6)
        mus *= (1 - 0.6 * np.clip(env * 3, 0, 1)).astype(np.float32)
        fade = int(0.6 * SR)
        mus[-fade:] *= np.linspace(1, 0, fade)
    out = voice * 1.0 + fx * 0.7 + mus * music_gain
    if base_audio is not None:
        out[: len(base_audio)] += base_audio[:n]
    peak = np.abs(out).max()
    if peak > 0.98:
        out = out / peak * 0.98
    return out


def write_wav(path, audio):
    import soundfile as sf
    sf.write(path, audio, SR)
