"""Free audio: Kokoro TTS (local), synthesized music bed and sound effects (no licensing issues)."""
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
    """Make numbers/abbreviations read naturally."""
    t = text.replace("GTA VI", "G T A six").replace("GTA 6", "G T A six")
    t = t.replace("GTA V ", "G T A five ").replace("GTA 5", "G T A five").replace("GTA IV", "G T A four")
    t = re.sub(r"\$(\d+(?:\.\d+)?)B\b", r"\1 billion dollars", t)
    t = re.sub(r"\$(\d+(?:\.\d+)?)M\b", r"\1 million dollars", t)
    return t


def tts(text: str, voice="am_michael", speed=1.12):
    """Returns (audio float32 @ SR, word timings list[{w,start,end}] relative to clip start)."""
    samples, sr = _kokoro().create(speak_text_prep(text), voice=voice, speed=speed, lang="en-us")
    samples = np.asarray(samples, np.float32)
    # trim leading/trailing silence
    nz = np.where(np.abs(samples) > 0.01)[0]
    if len(nz):
        samples = samples[max(0, nz[0] - int(0.02 * sr)): nz[-1] + int(0.05 * sr)]
    audio = resample_poly(samples, SR, sr).astype(np.float32)
    dur = len(audio) / SR
    words = text.split()
    # distribute word timings by character weight (good enough for captions)
    weights = np.array([len(re.sub(r"[^\w$%]", "", w)) + 2 for w in words], float)
    edges = np.concatenate([[0], np.cumsum(weights) / weights.sum()]) * dur
    timed = [{"w": w, "start": float(edges[i]), "end": float(edges[i + 1])} for i, w in enumerate(words)]
    return audio, timed


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
