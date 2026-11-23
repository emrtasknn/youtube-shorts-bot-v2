"""Music bed, a few quiet effects and the final mix for long-form films.

The bed is a slow, low pad (no drums, no risers). It sits ~20 dB under the voice,
stops for scenes marked ``music: false`` and turns to major chords from the scene
marked ``lift`` on. Effects are short and rare: typing under documents, one stamp
thump, one door thud.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import numpy.typing as npt
from scipy.signal import butter, sosfilt

from app.longform.frames import typing_window
from app.longform.spec import Film
from app.longform.timeline import Timeline
from app.studio.tts import SAMPLE_RATE

SR = SAMPLE_RATE
F64 = npt.NDArray[np.float64]

MINOR = [(50, 57, 65), (46, 53, 62), (41, 48, 57), (45, 52, 60)]  # Dm Bb F Am (midi)
MAJOR = [(41, 48, 57), (46, 53, 62), (48, 55, 64), (41, 48, 57)]  # F Bb C F
CHORD_SEC = 9.0


def _hz(m: int) -> float:
    return float(440.0 * 2 ** ((m - 69) / 12))


def _lp(x: F64, f: float) -> F64:
    return np.asarray(sosfilt(butter(2, f, "low", fs=SR, output="sos"), x), np.float64)


def _bp(x: F64, a: float, b: float) -> F64:
    return np.asarray(sosfilt(butter(2, [a, b], "band", fs=SR, output="sos"), x), np.float64)


def pad(duration: float, lift_at: float | None) -> F64:
    """Slow chord pad; every chord fades into the next."""
    n = int(duration * SR)
    out = np.zeros(n, np.float64)
    step = int(CHORD_SEC * SR)
    fade = int(3.0 * SR)
    k = 0
    for i0 in range(0, n, step):
        t0 = i0 / SR
        prog = MAJOR if lift_at is not None and t0 >= lift_at else MINOR
        chord = prog[k % len(prog)]
        k += 1
        length = min(step + fade, n - i0)
        t = np.arange(length) / SR
        seg = np.zeros(length)
        for j, m in enumerate(chord):
            f = _hz(m)
            vib = 1 + 0.002 * np.sin(2 * np.pi * (0.13 + 0.05 * j) * t)
            seg += np.sin(2 * np.pi * f * t * vib) + 0.25 * np.sin(4 * np.pi * f * t * vib)
        env = np.ones(length)
        r = min(fade, length // 2)
        env[:r] = np.linspace(0, 1, r)
        env[-r:] = np.minimum(env[-r:], np.linspace(1, 0, r))
        out[i0 : i0 + length] += seg * env
    out = _lp(out, 700.0)
    return np.asarray(out / (np.max(np.abs(out)) + 1e-9), np.float64)


def _gate(film: Film, tl: Timeline, n: int) -> F64:
    """1 where music plays, 0 where a scene asks for silence; 1.5 s ramps."""
    g = np.ones(n)
    for sc, slot in zip(film.scenes, tl.scenes, strict=True):
        if not sc.music:
            g[int(slot.start * SR) : int(slot.end * SR)] = 0
    k = int(1.5 * SR)
    kernel = np.ones(k) / k
    return np.clip(np.convolve(g, kernel, "same"), 0, 1)


def _typing(rng: np.random.Generator, t0: float, t1: float) -> list[tuple[float, F64]]:
    hits: list[tuple[float, F64]] = []
    t = t0
    while t < t1:
        n = int(0.018 * SR)
        click = rng.standard_normal(n) * np.exp(-np.linspace(0, 9, n))
        hits.append((t, _bp(click, 1800, 5200) * rng.uniform(0.5, 1.0)))
        t += rng.uniform(0.07, 0.16) + (0.35 if rng.random() < 0.08 else 0.0)
    return hits


def _thump(rng: np.random.Generator, freq: float, length: float) -> F64:
    n = int(length * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * freq * t) * np.exp(-t * 18)
    noise = _lp(rng.standard_normal(n), 900) * np.exp(-t * 30) * 0.6
    return np.asarray(body + noise, np.float64)


def effects(film: Film, tl: Timeline, n: int) -> F64:
    rng = np.random.default_rng(3)
    buf = np.zeros(n)

    def place(at: float, x: F64, gain: float) -> None:
        i = int(at * SR)
        j = min(i + len(x), n)
        if j > i >= 0:
            buf[i:j] += x[: j - i] * gain

    for si, (sc, slot) in enumerate(zip(film.scenes, tl.scenes, strict=True)):
        if sc.kind == "document" or sc.sfx == "typewriter":
            t0, t1 = typing_window(film, tl, si)
            for at, x in _typing(rng, t0, t1):
                place(at, x, 0.10)
            if sc.stamp:
                place(t1 + 0.35, _thump(rng, 70, 0.5), 0.5)
        if sc.sfx == "stamp":
            place(slot.end - 0.6, _thump(rng, 70, 0.5), 0.5)
        if sc.sfx == "door":
            place(slot.end - 0.5, _thump(rng, 48, 0.9), 0.65)
    return buf


def mix(film: Film, tl: Timeline, out_wav: Path) -> None:
    n = len(tl.voice)
    voice = tl.voice.astype(np.float64)
    lift = next(
        (slot.start for sc, slot in zip(film.scenes, tl.scenes, strict=True) if sc.lift), None
    )
    bed = pad(n / SR, lift) * _gate(film, tl, n) * 0.06
    sfx = effects(film, tl, n)
    master = voice + bed + sfx
    master /= max(float(np.max(np.abs(master))), 1.0)
    pcm = (np.clip(master, -1, 1) * 32767).astype(np.int16)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    import soundfile as sf

    sf.write(str(out_wav), pcm, SR, subtype="PCM_16")


def loudnorm(src: Path, dst: Path, target: float = -14.0) -> None:
    """YouTube plays at about -14 LUFS: two-pass ffmpeg loudnorm (measure, then apply)."""
    probe = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(src),
            "-af",
            f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    m = json.loads(probe[probe.rindex("{") : probe.rindex("}") + 1])
    flt = (
        f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:"
        f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
        f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-af",
            flt,
            "-ar",
            str(SR),
            str(dst),
        ],
        check=True,
    )
