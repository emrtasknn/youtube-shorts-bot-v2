from uuid import UUID

import pytest

from app.application.services.production_decision_safety import ProductionDecisionSafety
from app.domain.decision import ProductionDecision

POLICY_VERSION = "m10-v1"
APPLIED_ID = UUID("00000000-0000-0000-0000-000000000001")


def _decision() -> ProductionDecision:
    return ProductionDecision(
        decision_id=UUID("00000000-0000-0000-0000-000000000010"),
        policy_version=POLICY_VERSION,
        applied_recommendation_ids=(APPLIED_ID,),
        eligible_recommendation_ids=(APPLIED_ID,),
        input_recommendation_ids=(APPLIED_ID,),
    )


def test_accepts_matching_policy_and_unused_recommendation() -> None:
    ProductionDecisionSafety(POLICY_VERSION).validate(_decision())


def test_rejects_stale_policy_version() -> None:
    decision = ProductionDecision(
        decision_id=UUID("00000000-0000-0000-0000-000000000010"),
        policy_version="m10-old",
    )

    with pytest.raises(ValueError, match="does not match"):
        ProductionDecisionSafety(POLICY_VERSION).validate(decision)


def test_rejects_reuse_of_previously_applied_recommendation() -> None:
    with pytest.raises(ValueError, match="reuses already applied"):
        ProductionDecisionSafety(POLICY_VERSION).validate(
            _decision(),
            previously_applied_recommendation_ids=(str(APPLIED_ID),),
        )


def test_rollback_returns_empty_reversible_decision() -> None:
    rollback = ProductionDecisionSafety.rollback(policy_version=POLICY_VERSION)

    assert rollback.policy_version == POLICY_VERSION
    assert rollback.angle is None
    assert rollback.duration_target_seconds is None
    assert rollback.production_strategy is None
    assert rollback.applied_recommendation_ids == ()
    assert rollback.rejected_recommendation_ids == ()
