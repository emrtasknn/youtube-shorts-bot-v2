from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.decision import DecisionDimension, DecisionPolicy
from app.domain.learning import (
    ConfidenceLevel,
    LearningEvidence,
    LearningSignal,
    Recommendation,
    RecommendationStatus,
    SignalDirection,
)
from app.application.services.decision_policy import DecisionPolicyEngine


CREATED_AT = datetime(2026, 10, 5, tzinfo=UTC)


def _recommendation(
    *,
    feature: str = "angle",
    feature_value: str = "surprising",
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    direction: SignalDirection = SignalDirection.POSITIVE,
    delta: Decimal = Decimal("10"),
    status: RecommendationStatus = RecommendationStatus.GENERATED,
    recommendation_id: UUID | None = None,
) -> Recommendation:
    signal = LearningSignal(
        signal_id=uuid4(),
        feature=feature,
        feature_value=feature_value,
        metric="views",
        observed_value=Decimal("100") + delta,
        baseline_value=Decimal("100"),
        delta=delta,
        evidence=LearningEvidence(
            sample_size=10,
            baseline_available=True,
            data_quality_score=Decimal("1"),
        ),
        confidence=confidence,
        direction=direction,
        created_at=CREATED_AT,
    )
    return Recommendation(
        recommendation_id=recommendation_id or uuid4(),
        signal=signal,
        text="test recommendation",
        status=status,
        created_at=CREATED_AT,
    )


def _engine() -> DecisionPolicyEngine:
    return DecisionPolicyEngine(DecisionPolicy(policy_version="m10.2.v1"))


def test_applies_medium_confidence_positive_angle() -> None:
    recommendation = _recommendation(feature_value="contradiction")

    decision = _engine().decide([recommendation], created_at=CREATED_AT)

    assert decision.angle == "contradiction"
    assert decision.applied_recommendation_ids == (recommendation.recommendation_id,)
    assert decision.rejected_recommendation_ids == ()
    assert decision.policy_version == "m10.2.v1"


def test_rejects_low_confidence() -> None:
    recommendation = _recommendation(confidence=ConfidenceLevel.LOW)

    decision = _engine().decide([recommendation], created_at=CREATED_AT)

    assert decision.angle is None
    assert decision.applied_recommendation_ids == ()
    assert decision.rejected_recommendation_ids == (recommendation.recommendation_id,)
    assert "below the policy minimum" in decision.rationale[0]


def test_rejects_negative_signal_without_inverse_command() -> None:
    recommendation = _recommendation(
        direction=SignalDirection.NEGATIVE,
        delta=Decimal("-20"),
    )

    decision = _engine().decide([recommendation], created_at=CREATED_AT)

    assert decision.angle is None
    assert decision.applied_recommendation_ids == ()
    assert decision.rejected_recommendation_ids == (recommendation.recommendation_id,)
    assert "destructive production command" in decision.rationale[0]


def test_maps_duration_bucket_to_bounded_target() -> None:
    recommendation = _recommendation(
        feature="duration_bucket",
        feature_value="30-39s",
    )

    decision = _engine().decide([recommendation], created_at=CREATED_AT)

    assert decision.duration_target_seconds == Decimal("35")
    assert decision.applied_recommendation_ids == (recommendation.recommendation_id,)


def test_rejects_unsupported_feature() -> None:
    recommendation = _recommendation(
        feature="topic",
        feature_value="ancient Rome",
    )

    decision = _engine().decide([recommendation], created_at=CREATED_AT)

    assert decision.applied_recommendation_ids == ()
    assert decision.rejected_recommendation_ids == (recommendation.recommendation_id,)
    assert "not supported" in decision.rationale[0]


def test_same_dimension_conflict_is_deterministic() -> None:
    low_delta = _recommendation(
        feature_value="question",
        confidence=ConfidenceLevel.MEDIUM,
        delta=Decimal("5"),
        recommendation_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    high_delta = _recommendation(
        feature_value="contradiction",
        confidence=ConfidenceLevel.MEDIUM,
        delta=Decimal("20"),
        recommendation_id=UUID("00000000-0000-0000-0000-000000000002"),
    )

    decision = _engine().decide([low_delta, high_delta], created_at=CREATED_AT)

    assert decision.angle == "contradiction"
    assert decision.applied_recommendation_ids == (high_delta.recommendation_id,)
    assert decision.rejected_recommendation_ids == (low_delta.recommendation_id,)
    assert any("Conflict on angle" in item for item in decision.rationale)


def test_higher_confidence_wins_before_delta() -> None:
    medium = _recommendation(
        feature_value="question",
        confidence=ConfidenceLevel.MEDIUM,
        delta=Decimal("50"),
        recommendation_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    high = _recommendation(
        feature_value="contradiction",
        confidence=ConfidenceLevel.HIGH,
        delta=Decimal("1"),
        recommendation_id=UUID("00000000-0000-0000-0000-000000000002"),
    )

    decision = _engine().decide([medium, high], created_at=CREATED_AT)

    assert decision.angle == "contradiction"
    assert decision.applied_recommendation_ids == (high.recommendation_id,)
    assert decision.rejected_recommendation_ids == (medium.recommendation_id,)


def test_policy_can_disable_a_dimension() -> None:
    policy = DecisionPolicy(
        policy_version="m10.2.v1-angle-only",
        allowed_dimensions=(DecisionDimension.ANGLE,),
    )
    engine = DecisionPolicyEngine(policy)
    duration = _recommendation(
        feature="duration_bucket",
        feature_value="30-39s",
    )

    decision = engine.decide([duration], created_at=CREATED_AT)

    assert decision.duration_target_seconds is None
    assert decision.rejected_recommendation_ids == (duration.recommendation_id,)
