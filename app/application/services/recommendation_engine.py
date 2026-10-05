from __future__ import annotations

from collections.abc import Iterable
from uuid import NAMESPACE_URL, uuid5

from app.domain.learning import (
    ConfidenceLevel,
    LearningSignal,
    Recommendation,
    RecommendationStatus,
    SignalDirection,
)


class RecommendationEngine:
    """Convert sufficiently supported learning signals into explainable recommendations."""

    _ACTIONABLE_CONFIDENCE = frozenset(
        {
            ConfidenceLevel.LOW,
            ConfidenceLevel.MEDIUM,
            ConfidenceLevel.HIGH,
        }
    )

    def generate(self, signals: Iterable[LearningSignal]) -> tuple[Recommendation, ...]:
        recommendations = [
            self._build_recommendation(signal)
            for signal in signals
            if self._is_actionable(signal)
        ]
        return tuple(
            sorted(
                recommendations,
                key=lambda recommendation: (
                    recommendation.signal.feature,
                    recommendation.signal.feature_value,
                    recommendation.signal.metric,
                ),
            )
        )

    @classmethod
    def _is_actionable(cls, signal: LearningSignal) -> bool:
        return (
            signal.confidence in cls._ACTIONABLE_CONFIDENCE
            and signal.direction is not SignalDirection.NEUTRAL
            and signal.delta is not None
            and signal.evidence.baseline_available
        )

    @staticmethod
    def _build_recommendation(signal: LearningSignal) -> Recommendation:
        if signal.direction is SignalDirection.POSITIVE:
            action = "consider increasing"
            relation = "outperforms"
        else:
            action = "consider decreasing"
            relation = "underperforms"

        text = (
            f"For {signal.feature}='{signal.feature_value}', {signal.metric} "
            f"{relation} the comparable baseline by {signal.delta}. "
            f"Based on {signal.confidence.value} confidence evidence, {action} "
            f"reliance on this feature value in future content."
        )
        recommendation_id = uuid5(
            NAMESPACE_URL,
            (
                f"recommendation:{signal.signal_id}:{signal.feature}:"
                f"{signal.feature_value}:{signal.metric}"
            ),
        )
        return Recommendation(
            recommendation_id=recommendation_id,
            signal=signal,
            text=text,
            status=RecommendationStatus.GENERATED,
            created_at=signal.created_at,
        )
