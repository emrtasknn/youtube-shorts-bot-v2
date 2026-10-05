from decimal import Decimal
from uuid import UUID

import pytest

from app.application.services.experimentation import (
    ExperimentAnalysisService,
    ExperimentAssignmentService,
)
from app.domain.experimentation import (
    Experiment,
    ExperimentDimension,
    ExperimentStatus,
    ExperimentVariant,
    ExperimentOutcome,
)

EXPERIMENT_ID = UUID("00000000-0000-0000-0000-000000000301")
VARIANT_A = UUID("00000000-0000-0000-0000-000000000302")
VARIANT_B = UUID("00000000-0000-0000-0000-000000000303")


def _experiment(status: ExperimentStatus = ExperimentStatus.ACTIVE) -> Experiment:
    return Experiment(
        experiment_id=EXPERIMENT_ID,
        name="Angle test",
        status=status,
        dimension=ExperimentDimension.ANGLE,
        variants=(
            ExperimentVariant(VARIANT_A, "A", ExperimentDimension.ANGLE, "curiosity gap"),
            ExperimentVariant(VARIANT_B, "B", ExperimentDimension.ANGLE, "contradiction"),
        ),
        minimum_sample_size=2,
    )


def test_assignment_is_deterministic() -> None:
    service = ExperimentAssignmentService()
    first = service.assign(_experiment(), run_key="run-001")
    second = service.assign(_experiment(), run_key="run-001")

    assert first == second
    assert first.variant_id in {VARIANT_A, VARIANT_B}


def test_assignment_changes_with_run_key() -> None:
    service = ExperimentAssignmentService()
    assignments = {
        service.assign(_experiment(), run_key=f"run-{index}").variant_id
        for index in range(20)
    }

    assert assignments == {VARIANT_A, VARIANT_B}


def test_inactive_experiment_cannot_assign() -> None:
    with pytest.raises(ValueError, match="ACTIVE"):
        ExperimentAssignmentService().assign(
            _experiment(ExperimentStatus.DRAFT),
            run_key="run-001",
        )


def test_analysis_waits_for_minimum_sample() -> None:
    experiment = _experiment()
    outcomes = (
        (
            experiment.variants[0],
            ExperimentOutcome(
                assignment_id=UUID("00000000-0000-0000-0000-000000000304"),
                sample_count=1,
                average_views=Decimal("100"),
            ),
        ),
    )

    analysis = ExperimentAnalysisService().analyze(experiment, outcomes)

    assert analysis.ready is False
    assert analysis.winner_variant_id is None


def test_analysis_selects_highest_weighted_average() -> None:
    experiment = _experiment()
    outcomes = (
        (
            experiment.variants[0],
            ExperimentOutcome(
                assignment_id=UUID("00000000-0000-0000-0000-000000000304"),
                sample_count=2,
                average_views=Decimal("100"),
            ),
        ),
        (
            experiment.variants[1],
            ExperimentOutcome(
                assignment_id=UUID("00000000-0000-0000-0000-000000000305"),
                sample_count=2,
                average_views=Decimal("200"),
            ),
        ),
    )

    analysis = ExperimentAnalysisService().analyze(experiment, outcomes)

    assert analysis.ready is True
    assert analysis.winner_variant_id == VARIANT_B
    assert analysis.total_samples == 4
