from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.application.services.recommendation_engine import RecommendationEngine
from app.domain.learning import (
    ConfidenceLevel,
    LearningEvidence,
    LearningSignal,
    RecommendationStatus,
    SignalDirection,
)


def _signal(
    *,
    direction: SignalDirection,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    baseline_available: bool = True,
    delta: Decimal | None = Decimal("10"),
) -> LearningSignal:
    return LearningSignal(
        signal_id=uuid4(),
        feature="angle",
        feature_value="surprising",
        metric="views",
        observed_value=Decimal("110"),
        baseline_value=Decimal("100") if delta is not None else None,
        delta=delta,
        evidence=LearningEvidence(
            sample_size=10,
            baseline_available=baseline_available,
            data_quality_score=Decimal("1"),
        ),
        confidence=confidence,
        direction=direction,
        created_at=datetime(2026, 10, 5, tzinfo=UTC),
    )


def test_generates_positive_recommendation() -> None:
    recommendation = RecommendationEngine().generate(
        [_signal(direction=SignalDirection.POSITIVE)]
    )[0]

    assert recommendation.status is RecommendationStatus.GENERATED
    assert "outperforms" in recommendation.text
    assert "consider increasing" in recommendation.text
    assert recommendation.signal.direction is SignalDirection.POSITIVE


def test_generates_negative_recommendation() -> None:
    recommendation = RecommendationEngine().generate(
        [
            _signal(
                direction=SignalDirection.NEGATIVE,
                delta=Decimal("-10"),
            )
        ]
    )[0]

    assert "underperforms" in recommendation.text
    assert "consider decreasing" in recommendation.text


def test_skips_insufficient_and_neutral_signals() -> None:
    signals = [
        _signal(
            direction=SignalDirection.POSITIVE,
            confidence=ConfidenceLevel.INSUFFICIENT,
        ),
        _signal(direction=SignalDirection.NEUTRAL, delta=None),
    ]

    assert RecommendationEngine().generate(signals) == ()


def test_skips_signals_without_comparable_baseline() -> None:
    signal = _signal(
        direction=SignalDirection.POSITIVE,
        baseline_available=False,
    )

    assert RecommendationEngine().generate([signal]) == ()


def test_generates_deterministic_recommendation_id() -> None:
    signal = _signal(direction=SignalDirection.POSITIVE)

    first = RecommendationEngine().generate([signal])[0]
    second = RecommendationEngine().generate([signal])[0]

    assert first.recommendation_id == second.recommendation_id
