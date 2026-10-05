from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.decision import ProductionDecision


@dataclass(frozen=True, slots=True)
class ProductionDecisionAdapter:
    """Translate an auditable production decision into bounded generation inputs."""

    decision: ProductionDecision | None = None

    @property
    def angle(self) -> str | None:
        return self.decision.angle if self.decision is not None else None

    @property
    def duration_target_seconds(self) -> Decimal | None:
        return (
            self.decision.duration_target_seconds
            if self.decision is not None
            else None
        )

    @property
    def production_strategy(self) -> str | None:
        return (
            self.decision.production_strategy
            if self.decision is not None
            else None
        )

    def script_constraints(self) -> str:
        if self.decision is None:
            return "Target 25-40 seconds."

        constraints = []
        if self.angle:
            constraints.append(f"Use this content angle: {self.angle}.")
        if self.duration_target_seconds is not None:
            constraints.append(
                f"Target approximately {self.duration_target_seconds:g} seconds."
            )
        if not constraints:
            return "Target 25-40 seconds."
        return " ".join(constraints)
