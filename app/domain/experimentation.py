from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class ExperimentStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ExperimentDimension(StrEnum):
    TOPIC = "TOPIC"
    ANGLE = "ANGLE"
    DURATION_TARGET_SECONDS = "DURATION_TARGET_SECONDS"


class ExperimentAssignmentStatus(StrEnum):
    ASSIGNED = "ASSIGNED"
    COMPLETED = "COMPLETED"
    EXCLUDED = "EXCLUDED"


@dataclass(frozen=True, slots=True)
class ExperimentVariant:
    variant_id: UUID
    label: str
    dimension: ExperimentDimension
    value: str

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("variant label must not be empty")
        if not self.value.strip():
            raise ValueError("variant value must not be empty")


@dataclass(frozen=True, slots=True)
class Experiment:
    experiment_id: UUID
    name: str
    status: ExperimentStatus
    dimension: ExperimentDimension
    variants: tuple[ExperimentVariant, ...]
    minimum_sample_size: int = 10

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("experiment name must not be empty")
        if len(self.variants) < 2:
            raise ValueError("experiment requires at least two variants")
        if len({v.variant_id for v in self.variants}) != len(self.variants):
            raise ValueError("experiment variant IDs must be unique")
        if any(v.dimension is not self.dimension for v in self.variants):
            raise ValueError("all variants must use the experiment dimension")
        if self.minimum_sample_size <= 0:
            raise ValueError("minimum_sample_size must be positive")


@dataclass(frozen=True, slots=True)
class ExperimentAssignment:
    assignment_id: UUID
    experiment_id: UUID
    variant_id: UUID
    run_key: str
    status: ExperimentAssignmentStatus = ExperimentAssignmentStatus.ASSIGNED

    def __post_init__(self) -> None:
        if not self.run_key.strip():
            raise ValueError("assignment run_key must not be empty")


@dataclass(frozen=True, slots=True)
class ExperimentOutcome:
    assignment_id: UUID
    sample_count: int
    average_views: Decimal
    average_retention: Decimal | None = None
    engagement_rate: Decimal | None = None

    def __post_init__(self) -> None:
        if self.sample_count < 0:
            raise ValueError("sample_count must be non-negative")
        if self.average_views < 0:
            raise ValueError("average_views must be non-negative")
        if self.average_retention is not None and not 0 <= self.average_retention <= 1:
            raise ValueError("average_retention must be between 0 and 1")
        if self.engagement_rate is not None and self.engagement_rate < 0:
            raise ValueError("engagement_rate must be non-negative")


@dataclass(frozen=True, slots=True)
class ExperimentAnalysis:
    experiment_id: UUID
    ready: bool
    winner_variant_id: UUID | None
    total_samples: int
    rationale: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.total_samples < 0:
            raise ValueError("total_samples must be non-negative")
        if self.ready and self.winner_variant_id is None:
            raise ValueError("ready analysis requires a winner")
        if not self.rationale or any(not item.strip() for item in self.rationale):
            raise ValueError("analysis rationale is required")
