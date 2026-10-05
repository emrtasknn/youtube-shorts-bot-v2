from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid5

from app.domain.experimentation import (
    Experiment,
    ExperimentAnalysis,
    ExperimentAssignment,
    ExperimentOutcome,
    ExperimentStatus,
    ExperimentVariant,
)


@dataclass(frozen=True, slots=True)
class ExperimentAssignmentService:
    namespace: UUID = UUID("8d8c3d7a-0a4b-5e45-8d1d-4f4e2a4d3c11")

    def assign(self, experiment: Experiment, *, run_key: str) -> ExperimentAssignment:
        if experiment.status is not ExperimentStatus.ACTIVE:
            raise ValueError("experiment must be ACTIVE")
        key = f"{experiment.experiment_id}:{run_key}"
        digest = sha256(key.encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % len(experiment.variants)
        variant = sorted(experiment.variants, key=lambda item: str(item.variant_id))[index]
        assignment_id = uuid5(self.namespace, key)
        return ExperimentAssignment(
            assignment_id=assignment_id,
            experiment_id=experiment.experiment_id,
            variant_id=variant.variant_id,
            run_key=run_key,
        )


@dataclass(frozen=True, slots=True)
class ExperimentAnalysisService:
    """Analyze completed observations without changing production policy."""

    def analyze(
        self,
        experiment: Experiment,
        outcomes: tuple[tuple[ExperimentVariant, ExperimentOutcome], ...],
    ) -> ExperimentAnalysis:
        by_variant: dict[UUID, list[ExperimentOutcome]] = {
            v.variant_id: [] for v in experiment.variants
        }
        for variant, outcome in outcomes:
            if variant.variant_id not in by_variant:
                raise ValueError("outcome references an unknown experiment variant")
            by_variant[variant.variant_id].append(outcome)

        totals = {
            variant_id: sum(item.sample_count for item in items)
            for variant_id, items in by_variant.items()
        }
        total_samples = sum(totals.values())
        eligible = [
            variant_id
            for variant_id, count in totals.items()
            if count >= experiment.minimum_sample_size
        ]
        if len(eligible) != len(experiment.variants):
            return ExperimentAnalysis(
                experiment_id=experiment.experiment_id,
                ready=False,
                winner_variant_id=None,
                total_samples=total_samples,
                rationale=("Analysis waits until every variant reaches the minimum sample size.",),
            )

        averages: dict[UUID, Decimal] = {}
        for variant_id in eligible:
            items = by_variant[variant_id]
            samples = sum(item.sample_count for item in items)
            averages[variant_id] = (
                sum((item.average_views * item.sample_count for item in items), Decimal("0"))
                / samples
            )

        winner = min(
            eligible,
            key=lambda variant_id: (-averages[variant_id], str(variant_id)),
        )
        return ExperimentAnalysis(
            experiment_id=experiment.experiment_id,
            ready=True,
            winner_variant_id=winner,
            total_samples=total_samples,
            rationale=(
                "Analysis uses weighted average views among variants meeting minimum sample size.",
                "Winner selected deterministically by highest average views, then variant ID.",
            ),
        )
