from decimal import Decimal
from uuid import UUID

import pytest

from app.application.services.production_decision_adapter import ProductionDecisionAdapter
from app.application.services.production_decision_safety import ProductionDecisionSafety
from app.application.services.topic_selection_production_adapter import (
    TopicSelectionProductionAdapter,
)
from app.domain.decision import ProductionDecision
from app.domain.topic_optimization import (
    TopicDecisionStatus,
    TopicScore,
    TopicSelectionDecision,
)

POLICY_VERSION = "m10-v1"
CANDIDATE_ID = UUID("00000000-0000-0000-0000-000000000101")
DECISION_ID = UUID("00000000-0000-0000-0000-000000000102")


def _topic_decision() -> TopicSelectionDecision:
    return TopicSelectionDecision(
        decision_id=DECISION_ID,
        status=TopicDecisionStatus.SELECTED,
        selected_candidate_id=CANDIDATE_ID,
        selected_topic="The history of a vanished city",
        candidate_ids=(CANDIDATE_ID,),
        selected_score=TopicScore(candidate_id=CANDIDATE_ID, total=Decimal("0.9000")),
        rationale=("Selected by deterministic topic policy.",),
    )


def _production_decision(*, policy_version: str = POLICY_VERSION) -> ProductionDecision:
    return ProductionDecision(
        decision_id=UUID("00000000-0000-0000-0000-000000000103"),
        policy_version=policy_version,
        angle="curiosity gap",
        duration_target_seconds=Decimal("35"),
        production_strategy="custom_single_vertical_slice",
    )


def test_selected_topic_and_m10_decision_compose_without_cross_mutation() -> None:
    topic_decision = _topic_decision()
    production_decision = _production_decision()

    topic = TopicSelectionProductionAdapter(topic_decision).resolve_topic("Manual topic")
    adapter = ProductionDecisionAdapter(production_decision)

    assert topic == "The history of a vanished city"
    assert adapter.angle == "curiosity gap"
    assert adapter.duration_target_seconds == Decimal("35")
    assert adapter.production_strategy == "custom_single_vertical_slice"
    assert topic_decision == _topic_decision()
    assert production_decision == _production_decision()


def test_no_selection_preserves_m10_production_decision() -> None:
    topic_decision = TopicSelectionDecision.no_selection(decision_id=DECISION_ID)
    production_decision = _production_decision()

    topic = TopicSelectionProductionAdapter(topic_decision).resolve_topic("Manual topic")
    ProductionDecisionSafety(POLICY_VERSION).validate(production_decision)

    assert topic == "Manual topic"
    assert ProductionDecisionAdapter(production_decision).angle == "curiosity gap"


def test_stale_m10_decision_remains_rejected_with_topic_selection() -> None:
    topic = TopicSelectionProductionAdapter(_topic_decision()).resolve_topic("Manual topic")
    stale = _production_decision(policy_version="m10-old")

    with pytest.raises(ValueError, match="does not match"):
        ProductionDecisionSafety(POLICY_VERSION).validate(stale)

    assert topic == "The history of a vanished city"


def test_rollback_still_removes_m10_overrides_while_topic_selection_is_available() -> None:
    topic = TopicSelectionProductionAdapter(_topic_decision()).resolve_topic("Manual topic")
    rollback = ProductionDecisionSafety.rollback(policy_version=POLICY_VERSION)

    ProductionDecisionSafety(POLICY_VERSION).validate(rollback)

    adapter = ProductionDecisionAdapter(rollback)
    assert topic == "The history of a vanished city"
    assert adapter.angle is None
    assert adapter.duration_target_seconds is None
    assert adapter.production_strategy is None


def test_topic_selection_does_not_bypass_m10_recommendation_reuse_guard() -> None:
    topic = TopicSelectionProductionAdapter(_topic_decision()).resolve_topic("Manual topic")
    reused = ProductionDecision(
        decision_id=UUID("00000000-0000-0000-0000-000000000104"),
        policy_version=POLICY_VERSION,
        applied_recommendation_ids=(
            UUID("00000000-0000-0000-0000-000000000201"),
        ),
    )

    with pytest.raises(ValueError, match="reuses already applied"):
        ProductionDecisionSafety(POLICY_VERSION).validate(
            reused,
            previously_applied_recommendation_ids=(
                "00000000-0000-0000-0000-000000000201",
            ),
        )

    assert topic == "The history of a vanished city"
