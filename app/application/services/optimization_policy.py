from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from app.domain.experimentation import Experiment, ExperimentAnalysis, ExperimentOutcome
from app.domain.learning import ConfidenceLevel
from app.domain.optimization import (
    OptimizationDecision,
    OptimizationDecisionStatus,
    OptimizationPolicy,
)


@dataclass(frozen=True, slots=True)
class OptimizationPolicyService:
    """Promote experiment evidence only when the explicit policy gate passes."""

    policy: OptimizationPolicy

    def evaluate(
        self,
        experiment: Experiment,
        analysis: ExperimentAnalysis,
        outcomes: tuple[tuple[object, ExperimentOutcome], ...],
        *,
        control_variant_id: UUID,
    ) -> OptimizationDecision:
        decision_id = self._decision_id(
            experiment.experiment_id,
            analysis.winner_variant_id,
            control_variant_id,
        )
        if not analysis.ready or analysis.winner_variant_id is None:
            return OptimizationDecision.no_promotion(
                experiment_id=experiment.experiment_id,
                policy_version=self.policy.policy_version,
                rationale=("Experiment analysis is not ready for promotion.",),
                decision_id=decision_id,
            )

        if control_variant_id == analysis.winner_variant_id:
            return OptimizationDecision.no_promotion(
                experiment_id=experiment.experiment_id,
                policy_version=self.policy.policy_version,
                rationale=("Control variant cannot be promoted over itself.",),
                decision_id=decision_id,
            )

        averages, samples = self._averages(outcomes)
        control_average = averages.get(control_variant_id)
        winner_average = averages.get(analysis.winner_variant_id)
        winner_samples = samples.get(analysis.winner_variant_id, 0)
        if control_average is None or winner_average is None or control_average <= 0:
            return OptimizationDecision.no_promotion(
                experiment_id=experiment.experiment_id,
                policy_version=self.policy.policy_version,
                rationale=("Comparable control performance is unavailable.",),
                decision_id=decision_id,
            )

        uplift = ((winner_average - control_average) / control_average).quantize(Decimal("0.0001"))
        if uplift < self.policy.minimum_uplift:
            return OptimizationDecision.no_promotion(
                experiment_id=experiment.experiment_id,
                policy_version=self.policy.policy_version,
                rationale=(
                    f"Winner uplift {uplift} is below policy minimum {self.policy.minimum_uplift}.",
                ),
                decision_id=decision_id,
            )

        confidence = self._confidence(winner_samples)
        if self._rank(confidence) < self._rank(self.policy.minimum_confidence):
            return OptimizationDecision.no_promotion(
                experiment_id=experiment.experiment_id,
                policy_version=self.policy.policy_version,
                rationale=(
                    f"Winner evidence confidence {confidence} is below required "
                    f"{self.policy.minimum_confidence}.",
                ),
                decision_id=decision_id,
            )

        winner = next(
            variant for variant, _ in outcomes if variant.variant_id == analysis.winner_variant_id
        )
        return OptimizationDecision(
            decision_id=decision_id,
            policy_version=self.policy.policy_version,
            status=OptimizationDecisionStatus.PROMOTED,
            experiment_id=experiment.experiment_id,
            dimension=experiment.dimension,
            winner_variant_id=winner.variant_id,
            value=winner.value,
            control_variant_id=control_variant_id,
            uplift=uplift,
            confidence=confidence,
            rationale=(
                "Experiment analysis is ready and passed the optimization policy gate.",
                f"Winner uplift over control is {uplift}.",
                f"Winner evidence confidence is {confidence}.",
            ),
        )

    @staticmethod
    def _averages(
        outcomes: tuple[tuple[object, ExperimentOutcome], ...],
    ) -> tuple[dict[UUID, Decimal], dict[UUID, int]]:
        totals: dict[UUID, Decimal] = {}
        samples: dict[UUID, int] = {}
        for variant, outcome in outcomes:
            variant_id = variant.variant_id
            totals[variant_id] = totals.get(variant_id, Decimal("0")) + (
                outcome.average_views * outcome.sample_count
            )
            samples[variant_id] = samples.get(variant_id, 0) + outcome.sample_count
        return (
            {
                variant_id: total / samples[variant_id]
                for variant_id, total in totals.items()
                if samples[variant_id] > 0
            },
            samples,
        )

    @staticmethod
    def _confidence(sample_size: int) -> ConfidenceLevel:
        if sample_size == 0:
            return ConfidenceLevel.INSUFFICIENT
        if sample_size <= 2:
            return ConfidenceLevel.INSUFFICIENT
        if sample_size <= 5:
            return ConfidenceLevel.LOW
        if sample_size <= 14:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.HIGH

    @staticmethod
    def _rank(level: ConfidenceLevel) -> int:
        return {
            ConfidenceLevel.INSUFFICIENT: 0,
            ConfidenceLevel.LOW: 1,
            ConfidenceLevel.MEDIUM: 2,
            ConfidenceLevel.HIGH: 3,
        }[level]

    @staticmethod
    def _decision_id(
        experiment_id: UUID,
        winner_variant_id: UUID | None,
        control_variant_id: UUID,
    ) -> UUID:
        payload = {
            "experiment_id": str(experiment_id),
            "winner_variant_id": str(winner_variant_id) if winner_variant_id else None,
            "control_variant_id": str(control_variant_id),
        }
        return uuid5(
            NAMESPACE_URL,
            f"m13-optimization-v1:{json.dumps(payload, sort_keys=True, separators=(',', ':'))}",
        )
