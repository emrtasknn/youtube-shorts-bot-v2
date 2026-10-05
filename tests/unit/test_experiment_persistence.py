from unittest.mock import MagicMock
from uuid import UUID

from app.application.services.experiment_persistence import ExperimentPersistenceService
from app.domain.experimentation import (
    Experiment,
    ExperimentAssignment,
    ExperimentAssignmentStatus,
    ExperimentOutcome,
    ExperimentDimension,
    ExperimentStatus,
    ExperimentVariant,
)
from app.infrastructure.database.models import (
    ExperimentAssignmentModel,
    ExperimentModel,
    ExperimentOutcomeModel,
)

EXPERIMENT_ID = UUID("00000000-0000-0000-0000-000000000501")
VARIANT_A = UUID("00000000-0000-0000-0000-000000000502")
ASSIGNMENT_ID = UUID("00000000-0000-0000-0000-000000000503")


def _experiment() -> Experiment:
    return Experiment(
        experiment_id=EXPERIMENT_ID,
        name="Duration test",
        status=ExperimentStatus.ACTIVE,
        dimension=ExperimentDimension.DURATION_TARGET_SECONDS,
        variants=(
            ExperimentVariant(VARIANT_A, "A", ExperimentDimension.DURATION_TARGET_SECONDS, "25"),
            ExperimentVariant(
                UUID("00000000-0000-0000-0000-000000000504"),
                "B",
                ExperimentDimension.DURATION_TARGET_SECONDS,
                "35",
            ),
        ),
        minimum_sample_size=3,
    )


def test_experiment_persistence_is_idempotent() -> None:
    session = MagicMock()
    session.scalar.return_value = None
    experiment = _experiment()

    result = ExperimentPersistenceService(session).save_experiment(experiment)

    assert result == experiment
    model = session.add.call_args.args[0]
    assert isinstance(model, ExperimentModel)
    assert model.experiment_id == EXPERIMENT_ID
    assert model.variants[0]["value"] == "25"
    session.flush.assert_called_once()


def test_existing_experiment_is_returned_without_mutation() -> None:
    session = MagicMock()
    experiment = _experiment()
    model = ExperimentModel(
        id=UUID("00000000-0000-0000-0000-000000000505"),
        experiment_id=EXPERIMENT_ID,
        name=experiment.name,
        status=experiment.status.value,
        dimension=experiment.dimension.value,
        variants=[
            {
                "variant_id": str(v.variant_id),
                "label": v.label,
                "dimension": v.dimension.value,
                "value": v.value,
            }
            for v in experiment.variants
        ],
        minimum_sample_size=3,
    )
    session.scalar.return_value = model

    result = ExperimentPersistenceService(session).save_experiment(experiment)

    assert result == experiment
    session.add.assert_not_called()


def test_assignment_roundtrip() -> None:
    session = MagicMock()
    session.scalar.return_value = None
    assignment = ExperimentAssignment(
        ASSIGNMENT_ID,
        EXPERIMENT_ID,
        VARIANT_A,
        "run-1",
        ExperimentAssignmentStatus.ASSIGNED,
    )

    result = ExperimentPersistenceService(session).save_assignment(assignment)

    assert result == assignment
    row = session.add.call_args.args[0]
    assert isinstance(row, ExperimentAssignmentModel)
    assert row.assignment_id == ASSIGNMENT_ID

def test_outcome_must_match_assignment() -> None:
    session = MagicMock()
    session.scalar.return_value = None
    experiment = _experiment()
    assignment = ExperimentAssignment(
        ASSIGNMENT_ID,
        EXPERIMENT_ID,
        VARIANT_A,
        "run-1",
    )
    outcome = ExperimentOutcome(
        assignment_id=UUID("00000000-0000-0000-0000-000000000506"),
        sample_count=1,
        average_views=100,
    )

    with pytest.raises(ValueError, match="does not belong"):
        ExperimentPersistenceService(session).save_outcome(experiment, assignment, outcome)


def test_list_outcome_records_rehydrates_variants() -> None:
    session = MagicMock()
    experiment = _experiment()
    row = ExperimentOutcomeModel(
        id=UUID("00000000-0000-0000-0000-000000000507"),
        assignment_id=ASSIGNMENT_ID,
        experiment_id=EXPERIMENT_ID,
        variant_id=VARIANT_A,
        sample_count=2,
        average_views=125,
    )
    session.scalars.return_value.all.return_value = [row]

    records = ExperimentPersistenceService(session).list_outcome_records(experiment)

    assert records[0][0] == experiment.variants[0]
    assert records[0][1].assignment_id == ASSIGNMENT_ID
