from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VideoQualityExpectation:
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    duration_tolerance_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Video dimensions must be positive")
        if self.fps <= 0:
            raise ValueError("Video FPS must be positive")
        if self.duration_tolerance_seconds < 0:
            raise ValueError("Duration tolerance must not be negative")


@dataclass(frozen=True, slots=True)
class VideoQualityReport:
    passed: bool
    failures: tuple[str, ...]

    def ensure_passed(self) -> None:
        if not self.passed:
            raise RuntimeError("Video quality check failed: " + "; ".join(self.failures))


class VideoQualityGate:
    """Validates deterministic output properties without rendering or API calls."""

    def evaluate(
        self,
        *,
        duration_seconds: float,
        width: int,
        height: int,
        fps: float,
        has_audio: bool,
        expected_duration: float | None = None,
        expected: VideoQualityExpectation | None = None,
        require_audio: bool = False,
        subtitle_path_exists: bool = False,
        subtitles_expected: bool = False,
        scene_count: int | None = None,
        asset_count: int | None = None,
    ) -> VideoQualityReport:
        expectation = expected or VideoQualityExpectation()
        failures: list[str] = []

        if duration_seconds <= 0:
            failures.append("output duration must be positive")
        if width != expectation.width or height != expectation.height:
            failures.append(f"output dimensions must be {expectation.width}x{expectation.height}")
        if abs(fps - expectation.fps) > 0.01:
            failures.append(f"output FPS must be {expectation.fps:g}")
        if require_audio and not has_audio:
            failures.append("output audio stream is required")

        target_duration = expected_duration
        if (
            target_duration is not None
            and abs(duration_seconds - target_duration) > expectation.duration_tolerance_seconds
        ):
            failures.append(
                f"output duration differs from expected by more than "
                f"{expectation.duration_tolerance_seconds:g}s"
            )

        if subtitles_expected and not subtitle_path_exists:
            failures.append("subtitle file was expected but was not created")

        if scene_count is not None and scene_count <= 0:
            failures.append("scene count must be positive")
        if asset_count is not None and asset_count != scene_count:
            failures.append("asset count must match scene count")

        return VideoQualityReport(passed=not failures, failures=tuple(failures))
