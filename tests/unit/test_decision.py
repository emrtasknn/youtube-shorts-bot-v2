from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.decision import DecisionDimension, DecisionPolicy, ProductionDecision
from app.domain.learning import ConfidenceLevel


def test_decision_policy_defaults_to_medium_confidence() -> None:
    policy = DecisionPolicy(policy_version="m10-v1")

    assert policy.minimum_confidence is ConfidenceLevel.MEDIUM
    assert policy.allowed_dimensions == (
        DecisionDimension.ANGLE,
        DecisionDimension.DURATION_TARGET_SECONDS,
        DecisionDimension.PRODUCTION_STRATEGY,
    )


def test_decision_policy_requires_version_and_dimension() -> None:
    with pytest.raises(ValueError, match="policy_version"):
        DecisionPolicy(policy_version=" ")

    with pytest.raises(ValueError, match="at least one"):
        DecisionPolicy(policy_version="m10-v1", allowed_dimensions=())


def test_production_decision_validates_bounded_values() -> None:
    recommendation_id = uuid4()
    decision = ProductionDecision(
        decision_id=uuid4(),
        policy_version="m10-v1",
        angle="surprising fact",
        duration_target_seconds=Decimal("30"),
        production_strategy="balanced",
        input_recommendation_ids=(recommendation_id,),
        eligible_recommendation_ids=(recommendation_id,),
        applied_recommendation_ids=(recommendation_id,),
        rationale=("High-confidence positive signal.",),
        created_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
    )

    assert decision.angle == "surprising fact"
    assert decision.duration_target_seconds == Decimal("30")
    assert decision.applied_recommendation_ids == (recommendation_id,)


def test_production_decision_rejects_invalid_state() -> None:
    recommendation_id = uuid4()

    with pytest.raises(ValueError, match="positive"):
        ProductionDecision(
            decision_id=uuid4(),
            policy_version="m10-v1",
            duration_target_seconds=Decimal("0"),
        )

    with pytest.raises(ValueError, match="both applied and rejected"):
        ProductionDecision(
            decision_id=uuid4(),
            policy_version="m10-v1",
            applied_recommendation_ids=(recommendation_id,),
            rejected_recommendation_ids=(recommendation_id,),
        )

    with pytest.raises(ValueError, match="must not be blank"):
        ProductionDecision(
            decision_id=uuid4(),
            policy_version="m10-v1",
            rationale=(" ",),
        )


def test_empty_decision_is_safe_default() -> None:
    decision = ProductionDecision.empty(
        policy_version="m10-v1",
        created_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
    )

    assert decision.angle is None
    assert decision.duration_target_seconds is None
    assert decision.production_strategy is None
    assert not decision.applied_recommendation_ids
    assert decision.created_at == datetime(2026, 10, 5, 12, tzinfo=UTC)
