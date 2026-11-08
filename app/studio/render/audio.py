"""Procedural, licence-free music bed + sound design, and the final mix."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import numpy.typing as npt
from scipy.signal import butter, sosfilt

from app.studio.render.planner import Shot

SR = 48000
F64 = npt.NDArray[np.float64]


def _lp(x: F64, f: float) -> F64:
    return np.asarray(sosfilt(butter(4, f, "low", fs=SR, output="sos"), x), np.float64)


def _hp(x: F64, f: float) -> F64:
    return np.asarray(sosfilt(butter(4, f, "high", fs=SR, output="sos"), x), np.float64)


def _bp(x: F64, a: float, b: float) -> F64:
    b = min(b, SR / 2 - 100)
    return np.asarray(sosfilt(butter(2, [a, b], "band", fs=SR, output="sos"), x), np.float64)


def _place(buf: F64, x: F64, at: float) -> None:
    i = int(at * SR)
    j = min(i + len(x), len(buf))
    if j > i >= 0:
        buf[i:j] += x[: j - i]


class SoundDesigner:
    def __init__(self, seed: int = 7) -> None:
        self.rng = np.random.default_rng(seed)

    def thump(self, f0: float = 55, dur: float = 0.35) -> F64:
        tt = np.arange(int(dur * SR)) / SR
        return np.sin(2 * np.pi * (f0 + 60 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 9)

    def whoosh(self, dur: float = 0.45) -> F64:
        n = int(dur * SR)
        x = self.rng.standard_normal(n)
        out = np.zeros(n)
        for k in range(24):
            a, b = k * n // 24, (k + 1) * n // 24
            fr = 300 + (k / 24) * 4000
            out[a:b] = _bp(x[a:b], fr, fr * 1.8)
        return _lp(out * np.sin(np.linspace(0, np.pi, n)) ** 2, 7000) * 1.4

    def boom(self, dur: float = 1.6, f0: float = 42) -> F64:
        n = int(dur * SR)
        tt = np.arange(n) / SR
        b = np.sin(2 * np.pi * (f0 + 90 * np.exp(-tt * 18)) * tt) * np.exp(-tt * 2.8)
        crack = _hp(self.rng.standard_normal(n), 1500) * np.exp(-tt * 40) * 0.5
        return b + crack

    def riser(self, dur: float = 1.4) -> F64:
        n = int(dur * SR)
        tt = np.arange(n) / SR
        x = self.rng.standard_normal(n)
        out = np.zeros(n)
        for k in range(30):
            a, b = k * n // 30, (k + 1) * n // 30
            fr = 400 + (k / 30) ** 2 * 7000
            out[a:b] = _bp(x[a:b], fr, fr * 1.5)
        tone = np.sin(2 * np.pi * (200 + 600 * (tt / dur) ** 2) * tt) * 0.25
        return (out + tone) * (tt / dur) ** 2

    def zap(self, dur: float = 1.0) -> F64:
        n = int(dur * SR)
        tt = np.arange(n) / SR
        hum = np.sign(np.sin(2 * np.pi * 100 * tt)) * 0.3 + np.sin(2 * np.pi * 50 * tt) * 0.4
        sparks = _hp(self.rng.standard_normal(n), 3000) * (self.rng.random(n) < 0.004) * 3
        env = np.minimum(tt / 0.15, 1) * np.exp(-tt * 1.2)
        return np.asarray(_lp(hum, 2500) * env * 0.6 + sparks * np.exp(-tt * 2), np.float64)

    def music(self, duration: float, card_times: list[float], cut_times: list[float]) -> F64:
        n = int(duration * SR)
        t = np.arange(n) / SR
        bed = np.zeros(n)
        for f, g in [(55, 0.5), (55.3, 0.4), (82.4, 0.3), (110, 0.18), (130.8, 0.12)]:
            ph = 2 * np.pi * f * t + 0.3 * np.sin(2 * np.pi * 0.07 * t)
            saw = 2 * ((f * t + 0.05 * np.sin(2 * np.pi * 0.1 * t)) % 1) - 1
            bed += g * (0.6 * np.sin(ph) + 0.4 * saw)
        bed = _lp(bed, 420)
        bed += (
            _bp(self.rng.standard_normal(n), 2500, 6000)
            * 0.05
            * (0.6 + 0.4 * np.sin(2 * np.pi * 0.13 * t))
        )
        # heartbeat pulse that speeds up through the story
        pulse = np.zeros(n)
        bt = min(duration * 0.22, 12.0)
        while bt < duration - 0.5:
            if any(abs(bt - c) < 1.6 for c in card_times):
                bt += 0.5
                continue
            prog = bt / duration
            bpm = 70 + 25 * prog
            _place(pulse, 0.9 * self.thump(), bt)
            _place(pulse, 0.5 * self.thump(), bt + 0.22)
            bt += 60 / bpm
        bed += pulse
        # arrangement: dip into silence right before each card, then return
        keys_t = [0.0, 2.0]
        keys_v = [0.7, 0.55]
        for c in sorted(card_times):
            keys_t += [c - 1.4, c - 0.15, c + 0.25, c + 2.5]
            keys_v += [1.0, 0.0, 0.0, 0.75]
        keys_t += [max(duration - 3, keys_t[-1] + 0.1), duration]
        keys_v += [1.0, 0.9]
        order = np.argsort(keys_t)
        gain = np.interp(t, np.array(keys_t)[order], np.array(keys_v)[order])
        bed *= gain
        return np.asarray(bed / (np.max(np.abs(bed)) + 1e-9), np.float64)

    def sfx(self, duration: float, shots: list[Shot]) -> F64:
        n = int(duration * SR)
        buf = np.zeros(n)
        _place(buf, self.boom() * 0.9, 0.0)
        _place(buf, self.zap(1.0) * 0.4, 0.05)
        prev_vis = None
        for sh in shots[1:]:
            if sh.mode == "title":
                _place(buf, self.riser(1.3) * 0.7, sh.start - 1.3)
                _place(buf, self.boom(2.0, 36), sh.start)
            elif sh.visual != prev_vis:
                _place(buf, self.whoosh() * 0.55, max(sh.start - 0.3, 0))
            elif sh.era.value == "gold":
                _place(buf, self.boom(1.2, 70) * 0.35, sh.start)
            prev_vis = sh.visual
        _place(buf, self.riser(1.6) * 0.45, duration - 1.6)
        return np.asarray(buf / (np.max(np.abs(buf)) + 1e-9), np.float64)


def write_wav(path: Path, x: npt.NDArray[np.floating], sr: int = SR) -> None:
    import soundfile as sf

    sf.write(str(path), np.asarray(x, np.float32), sr, subtype="PCM_16")


def mix(voice: Path, music: Path, sfx: Path, out: Path) -> None:
    graph = (
        "[0:a]aresample=48000,highpass=f=70,"
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=80,"
        "equalizer=f=3500:t=q:w=1.2:g=2,equalizer=f=200:t=q:w=1:g=1.5,asplit=2[v][vsc];"
        "[1:a]volume=0.28[m];[m][vsc]sidechaincompress=threshold=0.03:ratio=6:"
        "attack=20:release=350[md];[2:a]volume=0.6[s];"
        "[v][md][s]amix=inputs=3:normalize=0:duration=longest,"
        "loudnorm=I=-14:TP=-1.5:LRA=9[out]"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(voice),
            "-i",
            str(music),
            "-i",
            str(sfx),
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        check=True,
    )
