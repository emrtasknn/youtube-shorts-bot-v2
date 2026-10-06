from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from app.application.services.audio_catalog import MusicTrack, SfxCue


_SAMPLE_RATE = 24_000
_MAX_AMPLITUDE = 0.22


def _write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767))
        for sample in samples
    )
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(_SAMPLE_RATE)
        output.writeframes(pcm)


class ProceduralMusicGenerator:
    """Generates original, deterministic instrumental beds; no external media API."""

    def generate(self, track: MusicTrack, *, duration_seconds: float, output_path: Path) -> Path:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        count = max(1, int(duration_seconds * _SAMPLE_RATE))
        beat = 60.0 / track.bpm
        scale = (220.0, 277.18, 329.63, 415.30)
        samples: list[float] = []
        for index in range(count):
            t = index / _SAMPLE_RATE
            phase = int(t / beat) % len(scale)
            frequency = scale[phase]
            envelope = min(1.0, t * 8.0) * min(1.0, max(0.0, duration_seconds - t) * 8.0)
            pulse = math.sin(2 * math.pi * frequency * t)
            harmonic = 0.35 * math.sin(2 * math.pi * frequency * 2 * t)
            samples.append(_MAX_AMPLITUDE * envelope * (pulse + harmonic) / 1.35)
        _write_wav(output_path, samples)
        return output_path


class ProceduralSfxGenerator:
    """Generates short original SFX cues from deterministic oscillators."""

    def generate(self, cue: SfxCue, *, output_path: Path) -> Path:
        duration = cue.duration_seconds
        count = max(1, int(duration * _SAMPLE_RATE))
        samples: list[float] = []
        for index in range(count):
            t = index / _SAMPLE_RATE
            progress = t / duration
            envelope = (1.0 - progress) ** 2
            if cue.kind == "impact":
                signal = math.sin(2 * math.pi * (90 + 50 * progress) * t)
            elif cue.kind == "whoosh":
                signal = math.sin(2 * math.pi * (250 + 900 * progress) * t)
            elif cue.kind == "alarm":
                signal = math.sin(
                    2 * math.pi * (700 if int(t * 8) % 2 else 1100) * t
                )
            else:
                signal = math.sin(2 * math.pi * 72 * t) + 0.25 * math.sin(
                    2 * math.pi * 144 * t
                )
            samples.append(0.35 * envelope * signal)
        _write_wav(output_path, samples)
        return output_path
