from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.optimization import OptimizationDecision, OptimizationDecisionStatus


@dataclass(frozen=True, slots=True)
class OptimizationDecisionSafety:
    """Validate optimization decisions before they can influence generation."""

    current_policy_version: str

    def validate(
        self,
        decision: OptimizationDecision,
        *,
        applied_decision_ids: tuple[UUID, ...] = (),
    ) -> None:
        if decision.policy_version != self.current_policy_version:
            raise ValueError("optimization decision policy version is stale")
        if decision.status is not OptimizationDecisionStatus.PROMOTED:
            return
        if decision.decision_id in set(applied_decision_ids):
            raise ValueError("optimization decision has already been applied")
        if decision.value is None or decision.dimension is None:
            raise ValueError("promoted optimization decision is incomplete")
