from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AudioQualityReport:
    passed: bool
    failures: tuple[str, ...]
    max_volume_dbfs: float | None = None
    mean_volume_dbfs: float | None = None
    silence_ratio: float | None = None

    def ensure_passed(self) -> None:
        if not self.passed:
            raise RuntimeError("Audio quality check failed: " + "; ".join(self.failures))


class AudioQualityGate:
    """Deterministic policy for the final mixed audio."""

    def evaluate(
        self,
        *,
        max_volume_dbfs: float,
        mean_volume_dbfs: float,
        silence_ratio: float,
    ) -> AudioQualityReport:
        failures: list[str] = []
        if max_volume_dbfs > -1.0:
            failures.append("audio peak is above -1 dBFS")
        if mean_volume_dbfs < -32.0 or mean_volume_dbfs > -8.0:
            failures.append("audio mean volume is outside the production range")
        if silence_ratio > 0.40:
            failures.append("audio silence ratio is too high")
        return AudioQualityReport(
            passed=not failures,
            failures=tuple(failures),
            max_volume_dbfs=max_volume_dbfs,
            mean_volume_dbfs=mean_volume_dbfs,
            silence_ratio=silence_ratio,
        )


def parse_ffmpeg_audio_metrics(stderr: str, *, duration_seconds: float) -> AudioQualityReport:
    max_match = re.search(r"max_volume:\s*(-?[\d.]+)\s*dB", stderr)
    mean_match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", stderr)
    silence_durations = [
        float(value)
        for value in re.findall(r"silence_duration:\s*([\d.]+)", stderr)
    ]
    max_volume = float(max_match.group(1)) if max_match else -100.0
    mean_volume = float(mean_match.group(1)) if mean_match else -100.0
    silence_total = sum(silence_durations)
    silence_ratio = min(1.0, silence_total / duration_seconds) if duration_seconds > 0 else 1.0
    return AudioQualityGate().evaluate(
        max_volume_dbfs=max_volume,
        mean_volume_dbfs=mean_volume,
        silence_ratio=silence_ratio,
    )


def validate_generated_wav(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 44:
        raise RuntimeError(f"Generated audio asset is missing or empty: {path}")
