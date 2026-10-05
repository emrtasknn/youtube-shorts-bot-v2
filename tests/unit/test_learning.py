from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.learning import (
    ConfidenceLevel,
    LearningEvidence,
    LearningSignal,
    Recommendation,
    RecommendationStatus,
    SignalDirection,
)


def make_evidence(*, sample_size: int = 12) -> LearningEvidence:
    return LearningEvidence(
        sample_size=sample_size,
        baseline_available=True,
        data_quality_score=Decimal("0.95"),
    )


def make_signal(*, confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM) -> LearningSignal:
    return LearningSignal(
        signal_id=uuid4(),
        feature="hook_type",
        feature_value="question",
        metric="retention",
        observed_value=Decimal("0.61"),
        baseline_value=Decimal("0.48"),
        delta=Decimal("0.13"),
        evidence=make_evidence(),
        confidence=confidence,
        direction=SignalDirection.POSITIVE,
        created_at=datetime(2026, 10, 5, tzinfo=UTC),
    )


def test_learning_evidence_is_immutable() -> None:
    evidence = make_evidence()

    with pytest.raises(AttributeError):
        evidence.sample_size = 10  # type: ignore[misc]


def test_learning_signal_contract_is_explainable() -> None:
    signal = make_signal()

    assert signal.feature == "hook_type"
    assert signal.feature_value == "question"
    assert signal.metric == "retention"
    assert signal.evidence.sample_size == 12
    assert signal.delta == Decimal("0.13")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("feature", ""),
        ("feature_value", ""),
        ("metric", ""),
    ],
)
def test_learning_signal_requires_identity_fields(field: str, value: str) -> None:
    values = {
        "feature": "hook_type",
        "feature_value": "question",
        "metric": "retention",
    }
    values[field] = value

    with pytest.raises(ValueError):
        LearningSignal(
            signal_id=uuid4(),
            observed_value=Decimal("0.61"),
            baseline_value=Decimal("0.48"),
            delta=Decimal("0.13"),
            evidence=make_evidence(),
            confidence=ConfidenceLevel.MEDIUM,
            direction=SignalDirection.POSITIVE,
            created_at=datetime(2026, 10, 5, tzinfo=UTC),
            **values,
        )


def test_delta_must_match_observed_minus_baseline() -> None:
    with pytest.raises(ValueError):
        LearningSignal(
            signal_id=uuid4(),
            feature="hook_type",
            feature_value="question",
            metric="retention",
            observed_value=Decimal("0.61"),
            baseline_value=Decimal("0.48"),
            delta=Decimal("0.10"),
            evidence=make_evidence(),
            confidence=ConfidenceLevel.MEDIUM,
            direction=SignalDirection.POSITIVE,
            created_at=datetime(2026, 10, 5, tzinfo=UTC),
        )


def test_zero_sample_signal_must_be_insufficient() -> None:
    with pytest.raises(ValueError):
        LearningSignal(
            signal_id=uuid4(),
            feature="hook_type",
            feature_value="question",
            metric="retention",
            observed_value=Decimal("0"),
            baseline_value=None,
            delta=None,
            evidence=make_evidence(sample_size=0),
            confidence=ConfidenceLevel.LOW,
            direction=SignalDirection.NEUTRAL,
            created_at=datetime(2026, 10, 5, tzinfo=UTC),
        )


def test_insufficient_signal_cannot_be_active_recommendation() -> None:
    signal = make_signal(confidence=ConfidenceLevel.INSUFFICIENT)

    with pytest.raises(ValueError):
        Recommendation(
            recommendation_id=uuid4(),
            signal=signal,
            text="Consider question-style hooks.",
            status=RecommendationStatus.ACTIVE,
            created_at=datetime(2026, 10, 5, tzinfo=UTC),
        )


def test_recommendation_requires_non_blank_text() -> None:
    with pytest.raises(ValueError):
        Recommendation(
            recommendation_id=uuid4(),
            signal=make_signal(),
            text="   ",
            status=RecommendationStatus.GENERATED,
            created_at=datetime(2026, 10, 5, tzinfo=UTC),
        )


def test_recommendation_keeps_signal_evidence() -> None:
    signal = make_signal()
    recommendation = Recommendation(
        recommendation_id=uuid4(),
        signal=signal,
        text="Consider question-style hooks.",
        status=RecommendationStatus.GENERATED,
        created_at=datetime(2026, 10, 5, tzinfo=UTC),
    )

    assert recommendation.signal.signal_id == signal.signal_id
    assert recommendation.signal.evidence.sample_size == 12
    assert recommendation.status is RecommendationStatus.GENERATED
