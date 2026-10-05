from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.experimentation import (
    Experiment,
    ExperimentAssignmentStatus,
    ExperimentDimension,
    ExperimentAssignment,
    ExperimentOutcome,
    ExperimentStatus,
    ExperimentVariant,
)
from app.infrastructure.database.models import (
    ExperimentAssignmentModel,
    ExperimentModel,
    ExperimentOutcomeModel,
)


class ExperimentPersistenceService:
    """Idempotent persistence for experimentation audit records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_experiment(self, experiment: Experiment) -> Experiment:
        existing = self._session.scalar(
            select(ExperimentModel).where(
                ExperimentModel.experiment_id == experiment.experiment_id
            )
        )
        if existing is not None:
            return self._to_experiment(existing)
        row = ExperimentModel(
            id=uuid4(),
            experiment_id=experiment.experiment_id,
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
            minimum_sample_size=experiment.minimum_sample_size,
        )
        self._session.add(row)
        self._session.flush()
        return experiment

    def save_assignment(self, assignment: ExperimentAssignment) -> ExperimentAssignment:
        existing = self._session.scalar(
            select(ExperimentAssignmentModel).where(
                ExperimentAssignmentModel.assignment_id == assignment.assignment_id
            )
        )
        if existing is not None:
            return self._to_assignment(existing)
        row = ExperimentAssignmentModel(
            id=uuid4(),
            assignment_id=assignment.assignment_id,
            experiment_id=assignment.experiment_id,
            variant_id=assignment.variant_id,
            run_key=assignment.run_key,
            status=assignment.status.value,
        )
        self._session.add(row)
        self._session.flush()
        return assignment

    def save_outcome(
        self,
        experiment: Experiment,
        assignment: ExperimentAssignment,
        outcome: ExperimentOutcome,
    ) -> ExperimentOutcome:
        if assignment.experiment_id != experiment.experiment_id:
            raise ValueError("assignment does not belong to experiment")
        existing = self._session.scalar(
            select(ExperimentOutcomeModel).where(
                ExperimentOutcomeModel.assignment_id == outcome.assignment_id
            )
        )
        if existing is not None:
            return self._to_outcome(existing)
        row = ExperimentOutcomeModel(
            id=uuid4(),
            assignment_id=outcome.assignment_id,
            experiment_id=experiment.experiment_id,
            variant_id=assignment.variant_id,
            sample_count=outcome.sample_count,
            average_views=outcome.average_views,
            average_retention=outcome.average_retention,
            engagement_rate=outcome.engagement_rate,
        )
        self._session.add(row)
        self._session.flush()
        return outcome

    def list_outcomes(self, experiment_id: UUID) -> tuple[ExperimentOutcome, ...]:
        rows = self._session.scalars(
            select(ExperimentOutcomeModel)
            .where(ExperimentOutcomeModel.experiment_id == experiment_id)
            .order_by(ExperimentOutcomeModel.created_at.asc(), ExperimentOutcomeModel.assignment_id.asc())
        ).all()
        return tuple(self._to_outcome(row) for row in rows)

    @staticmethod
    def _to_experiment(row: ExperimentModel) -> Experiment:
        variants = tuple(
            ExperimentVariant(
                variant_id=UUID(item["variant_id"]),
                label=item["label"],
                dimension=ExperimentDimension(item["dimension"]),
                value=item["value"],
            )
            for item in row.variants
        )
        return Experiment(
            experiment_id=row.experiment_id,
            name=row.name,
            status=ExperimentStatus(row.status),
            dimension=ExperimentDimension(row.dimension),
            variants=variants,
            minimum_sample_size=row.minimum_sample_size,
        )

    @staticmethod
    def _to_assignment(row: ExperimentAssignmentModel) -> ExperimentAssignment:
        return ExperimentAssignment(
            assignment_id=row.assignment_id,
            experiment_id=row.experiment_id,
            variant_id=row.variant_id,
            run_key=row.run_key,
            status=ExperimentAssignmentStatus(row.status),
        )

    @staticmethod
    def _to_outcome(row: ExperimentOutcomeModel) -> ExperimentOutcome:
        return ExperimentOutcome(
            assignment_id=row.assignment_id,
            sample_count=row.sample_count,
            average_views=Decimal(row.average_views),
            average_retention=Decimal(row.average_retention)
            if row.average_retention is not None
            else None,
            engagement_rate=Decimal(row.engagement_rate)
            if row.engagement_rate is not None
            else None,
        )
