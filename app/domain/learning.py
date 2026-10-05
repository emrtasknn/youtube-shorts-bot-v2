from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class ConfidenceLevel(StrEnum):
    """Evidence strength assigned to a deterministic learning signal."""

    INSUFFICIENT = "INSUFFICIENT"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SignalDirection(StrEnum):
    """Observed direction of a learning signal relative to its baseline."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


class RecommendationStatus(StrEnum):
    """Lifecycle state of a learning recommendation."""

    GENERATED = "GENERATED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    DISMISSED = "DISMISSED"


@dataclass(frozen=True, slots=True)
class LearningEvidence:
    """Evidence supporting a deterministic learning signal."""

    sample_size: int
    baseline_available: bool
    data_quality_score: Decimal
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")
        if not 0 <= self.data_quality_score <= 1:
            raise ValueError("data_quality_score must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class LearningSignal:
    """Deterministic, explainable signal extracted from performance memory."""

    signal_id: UUID
    feature: str
    feature_value: str
    metric: str
    observed_value: Decimal
    baseline_value: Decimal | None
    delta: Decimal | None
    evidence: LearningEvidence
    confidence: ConfidenceLevel
    direction: SignalDirection
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.feature:
            raise ValueError("feature is required")
        if not self.feature_value:
            raise ValueError("feature_value is required")
        if not self.metric:
            raise ValueError("metric is required")
        if self.evidence.sample_size == 0 and self.confidence is not ConfidenceLevel.INSUFFICIENT:
            raise ValueError("zero-sample signals must be INSUFFICIENT")
        if self.baseline_value is None and self.delta is not None:
            raise ValueError("delta requires baseline_value")
        if (
            self.baseline_value is not None
            and self.delta is not None
            and self.delta != self.observed_value - self.baseline_value
        ):
            raise ValueError("delta must equal observed_value - baseline_value")


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Explainable recommendation derived from a learning signal."""

    recommendation_id: UUID
    signal: LearningSignal
    text: str
    status: RecommendationStatus
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("recommendation text is required")
        if self.status is RecommendationStatus.ACTIVE and (
            self.signal.confidence is ConfidenceLevel.INSUFFICIENT
        ):
            raise ValueError("INSUFFICIENT signals cannot become ACTIVE recommendations")
