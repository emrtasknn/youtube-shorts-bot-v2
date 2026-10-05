from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.experimentation import ExperimentDimension
from app.domain.learning import ConfidenceLevel


class OptimizationDecisionStatus(StrEnum):
    PROMOTED = "PROMOTED"
    NO_PROMOTION = "NO_PROMOTION"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True, slots=True)
class OptimizationPolicy:
    """Immutable gate for promoting experiment evidence into production policy."""

    policy_version: str
    minimum_uplift: Decimal = Decimal("0.10")
    minimum_confidence: ConfidenceLevel = ConfidenceLevel.HIGH

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("optimization policy_version is required")
        if self.minimum_uplift < 0:
            raise ValueError("minimum uplift must be non-negative")


@dataclass(frozen=True, slots=True)
class OptimizationDecision:
    """Auditable, reversible production optimization decision."""

    decision_id: UUID
    policy_version: str
    status: OptimizationDecisionStatus
    experiment_id: UUID
    dimension: ExperimentDimension | None = None
    winner_variant_id: UUID | None = None
    value: str | None = None
    control_variant_id: UUID | None = None
    uplift: Decimal | None = None
    confidence: ConfidenceLevel = ConfidenceLevel.INSUFFICIENT
    rationale: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("optimization policy_version is required")
        if self.status is OptimizationDecisionStatus.PROMOTED:
            if self.dimension is None or self.winner_variant_id is None:
                raise ValueError("promoted decision requires a winner and dimension")
            if not self.value or self.control_variant_id is None:
                raise ValueError("promoted decision requires value and control variant")
            if self.uplift is None or self.uplift < 0:
                raise ValueError("promoted decision requires non-negative uplift")
            if self.confidence is ConfidenceLevel.INSUFFICIENT:
                raise ValueError("promoted decision requires sufficient confidence")
        if self.status is OptimizationDecisionStatus.NO_PROMOTION:
            if self.winner_variant_id is not None or self.value is not None:
                raise ValueError("no-promotion decisions cannot apply a variant")
        if self.uplift is not None and self.uplift < 0:
            raise ValueError("uplift must be non-negative")
        if not self.rationale or any(not item.strip() for item in self.rationale):
            raise ValueError("optimization rationale is required")

    @classmethod
    def no_promotion(
        cls,
        *,
        experiment_id: UUID,
        policy_version: str,
        rationale: tuple[str, ...],
        decision_id: UUID | None = None,
    ) -> OptimizationDecision:
        return cls(
            decision_id=decision_id or uuid4(),
            policy_version=policy_version,
            status=OptimizationDecisionStatus.NO_PROMOTION,
            experiment_id=experiment_id,
            rationale=rationale,
        )
