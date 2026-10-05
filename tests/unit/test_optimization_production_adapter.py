from decimal import Decimal
from uuid import UUID

import pytest

from app.application.services.optimization_production_adapter import (
    OptimizationProductionAdapter,
)
from app.domain.decision import ProductionDecision
from app.domain.experimentation import ExperimentDimension
from app.domain.learning import ConfidenceLevel
from app.domain.optimization import OptimizationDecision, OptimizationDecisionStatus
from app.domain.topic_optimization import TopicDecisionStatus, TopicScore, TopicSelectionDecision


def _decision(dimension: ExperimentDimension, value: str) -> OptimizationDecision:
    return OptimizationDecision(
        decision_id=UUID("00000000-0000-0000-0000-000000000701"),
        policy_version="m13-v1",
        status=OptimizationDecisionStatus.PROMOTED,
        experiment_id=UUID("00000000-0000-0000-0000-000000000702"),
        dimension=dimension,
        winner_variant_id=UUID("00000000-0000-0000-0000-000000000703"),
        value=value,
        control_variant_id=UUID("00000000-0000-0000-0000-000000000704"),
        uplift=Decimal("0.2"),
        confidence=ConfidenceLevel.HIGH,
        rationale=("promoted",),
    )


def test_promoted_angle_becomes_explicit_generation_input() -> None:
    override = OptimizationProductionAdapter().resolve(
        _decision(ExperimentDimension.ANGLE, "hidden detail")
    )
    assert override.angle == "hidden detail"


def test_no_promotion_has_no_override() -> None:
    decision = OptimizationDecision.no_promotion(
        experiment_id=UUID("00000000-0000-0000-0000-000000000705"),
        policy_version="m13-v1",
        rationale=("not enough evidence",),
    )
    assert OptimizationProductionAdapter().resolve(decision).angle is None


def test_optimization_angle_cannot_override_m10() -> None:
    production = ProductionDecision(
        decision_id=UUID("00000000-0000-0000-0000-000000000706"),
        policy_version="m10-v1",
        angle="explicit angle",
    )
    with pytest.raises(ValueError, match="ProductionDecision"):
        OptimizationProductionAdapter().resolve(
            _decision(ExperimentDimension.ANGLE, "optimized angle"),
            production_decision=production,
        )


def test_optimization_topic_cannot_override_m11() -> None:
    candidate_id = UUID("00000000-0000-0000-0000-000000000707")
    topic_decision = TopicSelectionDecision(
        decision_id=UUID("00000000-0000-0000-0000-000000000708"),
        status=TopicDecisionStatus.SELECTED,
        selected_candidate_id=candidate_id,
        selected_topic="Existing topic",
        candidate_ids=(candidate_id,),
        selected_score=TopicScore(candidate_id=candidate_id, total=Decimal("0.8")),
        rationale=("selected",),
    )
    with pytest.raises(ValueError, match="TopicSelectionDecision"):
        OptimizationProductionAdapter().resolve(
            _decision(ExperimentDimension.TOPIC, "optimized topic"),
            topic_selection_decision=topic_decision,
        )
