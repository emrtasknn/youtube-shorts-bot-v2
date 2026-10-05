from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class LearningFeature(StrEnum):
    """Production features currently eligible for deterministic learning."""

    CATEGORY = "category"
    ANGLE = "angle"
    DURATION_BUCKET = "duration_bucket"
    TOPIC = "topic"


@dataclass(frozen=True, slots=True)
class FeatureObservation:
    """Aggregated metric observation for one learning feature cohort."""

    feature: LearningFeature
    feature_value: str
    metric: str
    observed_value: Decimal
    sample_size: int

    def __post_init__(self) -> None:
        if not self.feature_value:
            raise ValueError("feature_value is required")
        if not self.metric:
            raise ValueError("metric is required")
        if self.sample_size <= 0:
            raise ValueError("sample_size must be positive")


def duration_bucket(seconds: Decimal | None) -> str | None:
    """Map target duration to a stable, deterministic learning bucket."""
    if seconds is None:
        return None
    if seconds < 20:
        return "<20s"
    if seconds < 30:
        return "20-29s"
    if seconds < 40:
        return "30-39s"
    if seconds < 50:
        return "40-49s"
    return "50s+"
