from decimal import Decimal
from uuid import UUID

import pytest

from app.application.services.optimization_policy import OptimizationPolicyService
from app.domain.experimentation import (
    Experiment,
    ExperimentAnalysis,
    ExperimentDimension,
    ExperimentOutcome,
    ExperimentStatus,
    ExperimentVariant,
)
from app.domain.learning import ConfidenceLevel
from app.domain.optimization import OptimizationDecisionStatus, OptimizationPolicy

EXPERIMENT_ID = UUID("00000000-0000-0000-0000-000000000601")
CONTROL_ID = UUID("00000000-0000-0000-0000-000000000602")
WINNER_ID = UUID("00000000-0000-0000-0000-000000000603")


def _experiment() -> Experiment:
    return Experiment(
        experiment_id=EXPERIMENT_ID,
        name="Angle test",
        status=ExperimentStatus.COMPLETED,
        dimension=ExperimentDimension.ANGLE,
        variants=(
            ExperimentVariant(CONTROL_ID, "control", ExperimentDimension.ANGLE, "historical fact"),
            ExperimentVariant(WINNER_ID, "winner", ExperimentDimension.ANGLE, "hidden detail"),
        ),
        minimum_sample_size=10,
    )


def _analysis() -> ExperimentAnalysis:
    return ExperimentAnalysis(
        experiment_id=EXPERIMENT_ID,
        ready=True,
        winner_variant_id=WINNER_ID,
        total_samples=40,
        rationale=("ready",),
    )


def _outcomes(winner_samples: int = 20) -> tuple[tuple[ExperimentVariant, ExperimentOutcome], ...]:
    experiment = _experiment()
    return (
        (
            experiment.variants[0],
            ExperimentOutcome(
                assignment_id=UUID("00000000-0000-0000-0000-000000000604"),
                sample_count=20,
                average_views=100,
            ),
        ),
        (
            experiment.variants[1],
            ExperimentOutcome(
                assignment_id=UUID("00000000-0000-0000-0000-000000000605"),
                sample_count=winner_samples,
                average_views=130,
            ),
        ),
    )


def test_promotes_high_confidence_winner_above_uplift_gate() -> None:
    decision = OptimizationPolicyService(
        OptimizationPolicy(
            policy_version="m13-v1",
            minimum_uplift=Decimal("0.10"),
            minimum_confidence=ConfidenceLevel.HIGH,
        )
    ).evaluate(
        _experiment(),
        _analysis(),
        _outcomes(),
        control_variant_id=CONTROL_ID,
    )

    assert decision.status is OptimizationDecisionStatus.PROMOTED
    assert decision.value == "hidden detail"
    assert decision.uplift == Decimal("0.3000")
    assert decision.confidence is ConfidenceLevel.HIGH


def test_rejects_below_uplift_gate() -> None:
    outcomes = (
        (
            _experiment().variants[0],
            ExperimentOutcome(
                assignment_id=UUID("00000000-0000-0000-0000-000000000606"),
                sample_count=20,
                average_views=100,
            ),
        ),
        (
            _experiment().variants[1],
            ExperimentOutcome(
                assignment_id=UUID("00000000-0000-0000-0000-000000000607"),
                sample_count=20,
                average_views=105,
            ),
        ),
    )
    decision = OptimizationPolicyService(
        OptimizationPolicy(policy_version="m13-v1")
    ).evaluate(_experiment(), _analysis(), outcomes, control_variant_id=CONTROL_ID)

    assert decision.status is OptimizationDecisionStatus.NO_PROMOTION
    assert decision.winner_variant_id is None


def test_rejects_medium_confidence_even_when_uplift_is_strong() -> None:
    decision = OptimizationPolicyService(
        OptimizationPolicy(policy_version="m13-v1", minimum_confidence=ConfidenceLevel.HIGH)
    ).evaluate(
        _experiment(),
        _analysis(),
        _outcomes(winner_samples=14),
        control_variant_id=CONTROL_ID,
    )

    assert decision.status is OptimizationDecisionStatus.NO_PROMOTION


def test_not_ready_analysis_cannot_promote() -> None:
    analysis = ExperimentAnalysis(
        experiment_id=EXPERIMENT_ID,
        ready=False,
        winner_variant_id=None,
        total_samples=10,
        rationale=("waiting",),
    )
    decision = OptimizationPolicyService(
        OptimizationPolicy(policy_version="m13-v1")
    ).evaluate(_experiment(), analysis, _outcomes(), control_variant_id=CONTROL_ID)

    assert decision.status is OptimizationDecisionStatus.NO_PROMOTION


def test_promotion_decision_is_deterministic() -> None:
    service = OptimizationPolicyService(OptimizationPolicy(policy_version="m13-v1"))
    first = service.evaluate(_experiment(), _analysis(), _outcomes(), control_variant_id=CONTROL_ID)
    second = service.evaluate(_experiment(), _analysis(), _outcomes(), control_variant_id=CONTROL_ID)

    assert first.decision_id == second.decision_id
