from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
@dataclass(frozen=True, slots=True)
class VideoJudgeInput:
    output_path: Path
    duration_seconds: float
    width: int
    height: int
    fps: float
    has_audio: bool
    expected_duration_seconds: float
    scene_count: int
    asset_count: int
    narration_word_count: int
    subtitle_text: str | None
    synchronization: dict[str, object]
    audio_qc_passed: bool
    audio_qc_failures: tuple[str, ...] = ()
    fallback_asset_count: int = 0


@dataclass(frozen=True, slots=True)
class VideoJudgeReport:
    decision: JudgeDecision
    score: float
    dimension_scores: dict[str, float]
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    retry_reasons: tuple[str, ...]
    evaluated_path: str

    @property
    def passed(self) -> bool:
        return self.decision in {"PASS", "PASS_WITH_WARNINGS"}

    def ensure_accepted(self) -> None:
        if not self.passed:
            raise RuntimeError(
                f"Automated video judge returned {self.decision}: "
                + "; ".join(self.failures or self.retry_reasons)
            )


class AutomatedVideoJudge:
    """Deterministic post-render quality decision layer.

    VideoQualityGate remains responsible for low-level render validity. This
    service combines that evidence with narrative, visual, audio, caption,
    synchronization and product signals and converts them into an auditable
    decision before approval.
    """

    def __init__(
        self,
        *,
        minimum_pass_score: float = 85.0,
        minimum_warning_score: float = 70.0,
        fallback_retry_ratio: float = 0.5,
    ) -> None:
        if not 0 < minimum_warning_score <= minimum_pass_score <= 100:
            raise ValueError("Judge score thresholds are invalid")
        if not 0 <= fallback_retry_ratio <= 1:
            raise ValueError("Fallback retry ratio must be between 0 and 1")
        self._minimum_pass_score = minimum_pass_score
        self._minimum_warning_score = minimum_warning_score
        self._fallback_retry_ratio = fallback_retry_ratio

    def evaluate(self, data: VideoJudgeInput) -> VideoJudgeReport:
        failures: list[str] = []
        warnings: list[str] = []
        retry_reasons: list[str] = []

        technical = 100.0
        narrative = 100.0
        visual = 100.0
        audio = 100.0
        captions = 100.0
        synchronization = 100.0
        product = 100.0

        if not data.output_path.is_file():
            failures.append("output file does not exist")
            technical = 0.0
        if data.width != 1080 or data.height != 1920:
            failures.append("output dimensions are not 1080x1920")
            technical = 0.0
        if abs(data.fps - 30.0) > 0.01:
            failures.append("output FPS is not 30")
            technical = 0.0
        if not data.has_audio:
            failures.append("output audio stream is missing")
            technical = 0.0
            audio = 0.0
        if data.duration_seconds <= 0:
            failures.append("output duration is not positive")
            technical = 0.0
        duration_delta = abs(data.duration_seconds - data.expected_duration_seconds)
        if duration_delta > 0.75:
            failures.append("output duration materially differs from expected duration")
            technical = min(technical, 40.0)
        elif duration_delta > 0.25:
            warnings.append("output duration is slightly outside the preferred tolerance")
            technical = min(technical, 85.0)

        if data.scene_count <= 0:
            failures.append("video contains no scenes")
            narrative = 0.0
            visual = 0.0
        if data.asset_count < data.scene_count:
            failures.append("visual asset coverage is below the scene count")
            visual = 0.0
        if data.narration_word_count < 35:
            failures.append("narration is below the minimum short-form story length")
            narrative = 0.0

        if data.audio_qc_failures or not data.audio_qc_passed:
            warnings.append("audio QC reported failures")
            audio = 65.0
            retry_reasons.append("audio_qc_failed")

        if data.subtitle_text and not data.subtitle_text.strip():
            warnings.append("subtitle text is empty")
            captions = 60.0

        sync_issues = data.synchronization.get("issues", [])
        if isinstance(sync_issues, list):
            errors = [
                item for item in sync_issues
                if isinstance(item, dict) and item.get("severity") == "error"
            ]
            if errors:
                failures.append("synchronization contains blocking errors")
                synchronization = 0.0
            elif sync_issues:
                warnings.append("synchronization contains non-blocking issues")
                synchronization = 90.0

        if data.fallback_asset_count:
            ratio = data.fallback_asset_count / max(data.scene_count, 1)
            if ratio >= self._fallback_retry_ratio:
                retry_reasons.append("excessive_visual_fallbacks")
                visual = 60.0
            else:
                warnings.append("one or more scenes used visual fallback")
                visual = 90.0

        if data.duration_seconds > 60.0:
            failures.append("output exceeds the Shorts duration ceiling")
            product = 0.0
        elif data.duration_seconds > 59.0:
            warnings.append("output is very close to the Shorts duration ceiling")
            product = 90.0

        if failures:
            decision: JudgeDecision = "REJECT"
        elif retry_reasons:
            decision = "RETRY"
        else:
            scores = {
                "technical": technical,
                "narrative": narrative,
                "visual": visual,
                "audio": audio,
                "captions": captions,
                "synchronization": synchronization,
                "product": product,
            }
            score = sum(scores.values()) / len(scores)
            if score >= self._minimum_pass_score and not warnings:
                decision = "PASS"
            elif score >= self._minimum_warning_score:
                decision = "PASS_WITH_WARNINGS"
            else:
                decision = "RETRY"

        scores = {
            "technical": technical,
            "narrative": narrative,
            "visual": visual,
            "audio": audio,
            "captions": captions,
            "synchronization": synchronization,
            "product": product,
        }
        score = round(sum(scores.values()) / len(scores), 2)
        return VideoJudgeReport(
            decision=decision,
            score=score,
            dimension_scores=scores,
            failures=tuple(failures),
            warnings=tuple(warnings),
            retry_reasons=tuple(retry_reasons),
            evaluated_path=str(data.output_path),
        )
