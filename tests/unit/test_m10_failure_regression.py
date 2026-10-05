from decimal import Decimal
from uuid import UUID

import pytest

from app.application.services.production_decision_adapter import ProductionDecisionAdapter
from app.application.services.production_decision_safety import ProductionDecisionSafety
from app.domain.decision import ProductionDecision

POLICY_VERSION = "m10-v1"
FIRST_ID = UUID("00000000-0000-0000-0000-000000000001")
SECOND_ID = UUID("00000000-0000-0000-0000-000000000002")


def _decision(*, applied_ids: tuple[UUID, ...] = (FIRST_ID,)) -> ProductionDecision:
    return ProductionDecision(
        decision_id=UUID("00000000-0000-0000-0000-000000000010"),
        policy_version=POLICY_VERSION,
        angle="curiosity gap",
        duration_target_seconds=Decimal("35"),
        applied_recommendation_ids=applied_ids,
        eligible_recommendation_ids=applied_ids,
        input_recommendation_ids=applied_ids,
    )


def test_stale_decision_is_rejected_before_generation_adapter() -> None:
    decision = ProductionDecision(
        decision_id=UUID("00000000-0000-0000-0000-000000000010"),
        policy_version="m10-old",
    )

    with pytest.raises(ValueError, match="does not match"):
        ProductionDecisionSafety(POLICY_VERSION).validate(decision)

    assert ProductionDecisionAdapter(decision).script_constraints() == "Target 25-40 seconds."


def test_any_reused_recommendation_blocks_the_decision() -> None:
    decision = _decision(applied_ids=(FIRST_ID, SECOND_ID))

    with pytest.raises(ValueError, match="00000000-0000-0000-0000-000000000001"):
        ProductionDecisionSafety(POLICY_VERSION).validate(
            decision,
            previously_applied_recommendation_ids=(str(FIRST_ID),),
        )


def test_rollback_restores_pre_m10_generation_defaults() -> None:
    rollback = ProductionDecisionSafety.rollback(policy_version=POLICY_VERSION)

    ProductionDecisionSafety(POLICY_VERSION).validate(rollback)

    adapter = ProductionDecisionAdapter(rollback)
    assert adapter.angle is None
    assert adapter.duration_target_seconds is None
    assert adapter.production_strategy is None
    assert adapter.script_constraints() == "Target 25-40 seconds."


def test_unused_recommendations_remain_eligible_for_a_later_decision() -> None:
    decision = _decision(applied_ids=(SECOND_ID,))

    ProductionDecisionSafety(POLICY_VERSION).validate(
        decision,
        previously_applied_recommendation_ids=(str(FIRST_ID),),
    )


def test_safety_validation_does_not_mutate_decision() -> None:
    decision = _decision(applied_ids=(FIRST_ID, SECOND_ID))
    before = decision

    ProductionDecisionSafety(POLICY_VERSION).validate(decision)

    assert decision == before
