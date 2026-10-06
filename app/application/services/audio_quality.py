from __future__ import annotations

import asyncio
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


class AudioQualityAnalyzer:
    """Runs one bounded FFmpeg audio analysis against the rendered MP4."""

    def __init__(self, executable: str = "ffmpeg", timeout_seconds: float = 90.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Audio QC timeout must be positive")
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    async def analyze_file(self, path: Path, *, duration_seconds: float) -> AudioQualityReport:
        if not path.is_file():
            raise FileNotFoundError(path)
        process = await asyncio.create_subprocess_exec(
            self._executable,
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "volumedetect,silencedetect=noise=-45dB:d=0.15",
            "-f",
            "null",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=self._timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError("Audio QC analysis timed out") from exc
        if process.returncode != 0:
            raise RuntimeError(
                "Audio QC analysis failed: " + stderr.decode("utf-8", errors="replace").strip()
            )
        return parse_ffmpeg_audio_metrics(
            stderr.decode("utf-8", errors="replace"),
            duration_seconds=duration_seconds,
        )


def parse_ffmpeg_audio_metrics(stderr: str, *, duration_seconds: float) -> AudioQualityReport:
    max_match = re.search(r"max_volume:\s*(-?[\d.]+)\s*dB", stderr)
    mean_match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", stderr)
    silence_durations = [
        float(value) for value in re.findall(r"silence_duration:\s*([\d.]+)", stderr)
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
