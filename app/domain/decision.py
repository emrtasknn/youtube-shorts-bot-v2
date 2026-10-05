from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.learning import ConfidenceLevel


class DecisionDimension(StrEnum):
    """Production dimensions that M10 may explicitly control."""

    ANGLE = "angle"
    DURATION_TARGET_SECONDS = "duration_target_seconds"
    PRODUCTION_STRATEGY = "production_strategy"


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    """Immutable configuration for controlled recommendation application."""

    policy_version: str
    minimum_confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    allowed_dimensions: tuple[DecisionDimension, ...] = (
        DecisionDimension.ANGLE,
        DecisionDimension.DURATION_TARGET_SECONDS,
        DecisionDimension.PRODUCTION_STRATEGY,
    )

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("policy_version is required")
        if not self.allowed_dimensions:
            raise ValueError("at least one decision dimension is required")


@dataclass(frozen=True, slots=True)
class ProductionDecision:
    """Immutable, auditable production overrides derived from policy."""

    decision_id: UUID
    policy_version: str
    angle: str | None = None
    duration_target_seconds: Decimal | None = None
    production_strategy: str | None = None
    applied_recommendation_ids: tuple[UUID, ...] = ()
    rejected_recommendation_ids: tuple[UUID, ...] = ()
    rationale: tuple[str, ...] = ()
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("policy_version is required")
        if self.duration_target_seconds is not None and self.duration_target_seconds <= 0:
            raise ValueError("duration_target_seconds must be positive")
        if any(not item.strip() for item in self.rationale):
            raise ValueError("decision rationale entries must not be blank")
        if set(self.applied_recommendation_ids) & set(self.rejected_recommendation_ids):
            raise ValueError("a recommendation cannot be both applied and rejected")

    @classmethod
    def empty(cls, *, policy_version: str, created_at: datetime | None = None) -> ProductionDecision:
        return cls(
            decision_id=uuid4(),
            policy_version=policy_version,
            created_at=created_at,
        )
