from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.decision import ProductionDecision
from app.application.services.optimization_safety import OptimizationDecisionSafety
from app.domain.optimization import OptimizationDecision, OptimizationDecisionStatus
from app.domain.topic_optimization import TopicDecisionStatus, TopicSelectionDecision


@dataclass(frozen=True, slots=True)
class OptimizationProductionOverride:
    topic: str | None = None
    angle: str | None = None
    duration_target_seconds: Decimal | None = None


@dataclass(frozen=True, slots=True)
class OptimizationProductionAdapter:
    """Translate a promoted optimization decision into bounded generation input."""

    current_policy_version: str = "m13-v1"

    def resolve(
        self,
        decision: OptimizationDecision,
        *,
        production_decision: ProductionDecision | None = None,
        topic_selection_decision: TopicSelectionDecision | None = None,
    ) -> OptimizationProductionOverride:
        OptimizationDecisionSafety(self.current_policy_version).validate(decision)
        if decision.status is not OptimizationDecisionStatus.PROMOTED:
            return OptimizationProductionOverride()

        if not decision.value or decision.dimension is None:
            raise ValueError("promoted optimization decision is incomplete")

        if decision.dimension.value == "TOPIC":
            if (
                topic_selection_decision is not None
                and topic_selection_decision.status is TopicDecisionStatus.SELECTED
            ):
                raise ValueError("optimization topic conflicts with TopicSelectionDecision")
            return OptimizationProductionOverride(topic=decision.value)

        if decision.dimension.value == "ANGLE":
            if production_decision is not None and production_decision.angle is not None:
                raise ValueError("optimization angle conflicts with ProductionDecision")
            return OptimizationProductionOverride(angle=decision.value)

        if decision.dimension.value == "DURATION_TARGET_SECONDS":
            if (
                production_decision is not None
                and production_decision.duration_target_seconds is not None
            ):
                raise ValueError("optimization duration conflicts with ProductionDecision")
            duration = Decimal(decision.value)
            if duration <= 0:
                raise ValueError("optimization duration must be positive")
            return OptimizationProductionOverride(duration_target_seconds=duration)

        raise ValueError("unsupported optimization dimension")
