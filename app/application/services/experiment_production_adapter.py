from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.decision import ProductionDecision
from app.domain.experimentation import ExperimentDimension, ExperimentVariant
from app.domain.topic_optimization import TopicDecisionStatus, TopicSelectionDecision


@dataclass(frozen=True, slots=True)
class ExperimentProductionOverride:
    topic: str | None = None
    angle: str | None = None
    duration_target_seconds: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ExperimentProductionAdapter:
    """Apply one explicit experiment variant without bypassing M10 decisions."""

    def resolve(
        self,
        variant: ExperimentVariant,
        *,
        production_decision: ProductionDecision | None = None,
        topic_selection_decision: TopicSelectionDecision | None = None,
    ) -> ExperimentProductionOverride:
        decision = production_decision
        if variant.dimension is ExperimentDimension.TOPIC:
            if (
                topic_selection_decision is not None
                and topic_selection_decision.status is TopicDecisionStatus.SELECTED
            ):
                raise ValueError("experiment topic conflicts with TopicSelectionDecision")
            return ExperimentProductionOverride(topic=variant.value)
        if variant.dimension is ExperimentDimension.ANGLE:
            if decision is not None and decision.angle is not None:
                raise ValueError("experiment angle conflicts with ProductionDecision")
            return ExperimentProductionOverride(angle=variant.value)
        if variant.dimension is ExperimentDimension.DURATION_TARGET_SECONDS:
            if decision is not None and decision.duration_target_seconds is not None:
                raise ValueError("experiment duration conflicts with ProductionDecision")
            try:
                duration = Decimal(variant.value)
            except Exception as exc:
                raise ValueError("experiment duration must be numeric") from exc
            if duration <= 0:
                raise ValueError("experiment duration must be positive")
            return ExperimentProductionOverride(duration_target_seconds=duration)
        raise ValueError("unsupported experiment dimension")
