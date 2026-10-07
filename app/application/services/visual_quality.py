from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class VisualQualityDecision(StrEnum):
    ACCEPT = "accept"
    BEAUTIFY = "beautify"
    ACCEPT_DEGRADED = "accept_degraded"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class VisualQualityScore:
    """Normalized visual-quality evidence for one retrieved asset."""

    composition: float
    resolution: float
    portrait_fit: float
    cleanliness: float
    overall: float
    beautifiable: bool

    def __post_init__(self) -> None:
        for name, value in (
            ("composition", self.composition),
            ("resolution", self.resolution),
            ("portrait_fit", self.portrait_fit),
            ("cleanliness", self.cleanliness),
            ("overall", self.overall),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class VisualQualityDecisionResult:
    decision: VisualQualityDecision
    score: VisualQualityScore
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VisualQualityPolicy:
    """Conservative quality policy; semantic relevance remains an M17 concern."""

    accept_threshold: float = 0.75
    beautify_threshold: float = 0.55
    degraded_floor: float = 0.40

    def __post_init__(self) -> None:
        if not (
            0.0 <= self.degraded_floor <= self.beautify_threshold <= self.accept_threshold <= 1.0
        ):
            raise ValueError("Quality thresholds must be ordered between 0 and 1")


class VisualQualityEvaluator:
    """Evaluates render suitability without changing M17 semantic relevance."""

    def __init__(self, policy: VisualQualityPolicy | None = None) -> None:
        self._policy = policy or VisualQualityPolicy()

    def evaluate(
        self,
        *,
        composition: float,
        resolution: float,
        portrait_fit: float,
        cleanliness: float,
        beautifiable: bool,
    ) -> VisualQualityDecisionResult:
        score = VisualQualityScore(
            composition=self._clamp(composition),
            resolution=self._clamp(resolution),
            portrait_fit=self._clamp(portrait_fit),
            cleanliness=self._clamp(cleanliness),
            overall=self._overall(
                composition,
                resolution,
                portrait_fit,
                cleanliness,
            ),
            beautifiable=beautifiable,
        )

        if score.overall >= self._policy.accept_threshold:
            return VisualQualityDecisionResult(
                VisualQualityDecision.ACCEPT,
                score,
                ("quality_above_accept_threshold",),
            )

        if score.overall >= self._policy.beautify_threshold and beautifiable:
            return VisualQualityDecisionResult(
                VisualQualityDecision.BEAUTIFY,
                score,
                ("quality_is_improvable",),
            )

        if score.overall >= self._policy.degraded_floor:
            return VisualQualityDecisionResult(
                VisualQualityDecision.ACCEPT_DEGRADED,
                score,
                ("quality_below_preferred_threshold",),
            )

        return VisualQualityDecisionResult(
            VisualQualityDecision.REJECT,
            score,
            ("quality_below_safe_floor",),
        )

    @staticmethod
    def _overall(
        composition: float,
        resolution: float,
        portrait_fit: float,
        cleanliness: float,
    ) -> float:
        return max(
            0.0,
            min(
                1.0,
                composition * 0.30
                + resolution * 0.30
                + portrait_fit * 0.25
                + cleanliness * 0.15,
            ),
        )

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))
