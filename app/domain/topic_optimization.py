from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4


class TopicEvidenceType(StrEnum):
    """Evidence sources allowed to influence bounded topic selection."""

    CANDIDATE_METADATA = "candidate_metadata"
    HISTORICAL_PERFORMANCE = "historical_performance"
    NOVELTY = "novelty"


class TopicDecisionStatus(StrEnum):
    """Lifecycle state of a topic selection decision."""

    SELECTED = "selected"
    NO_SELECTION = "no_selection"


@dataclass(frozen=True, slots=True)
class TopicCandidate:
    """Immutable topic candidate presented to the M11 optimizer."""

    candidate_id: UUID
    title: str
    source: str
    angle: str | None = None
    relevance_score: Decimal | None = None
    novelty_score: Decimal | None = None
    trend_score: Decimal | None = None
    evergreen_score: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("topic title is required")
        if not self.source.strip():
            raise ValueError("topic source is required")
        for name in (
            "relevance_score",
            "novelty_score",
            "trend_score",
            "evergreen_score",
        ):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class TopicEvidence:
    """Explainable evidence attached to one topic candidate."""

    evidence_type: TopicEvidenceType
    value: Decimal
    sample_size: int = 0
    confidence: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 1:
            raise ValueError("evidence value must be between 0 and 1")
        if self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class TopicScore:
    """Deterministic score and rationale for one candidate."""

    candidate_id: UUID
    total: Decimal
    evidence: tuple[TopicEvidence, ...] = ()
    rationale: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.total <= 1:
            raise ValueError("topic score must be between 0 and 1")
        if any(not item.strip() for item in self.rationale):
            raise ValueError("topic rationale entries must not be blank")


@dataclass(frozen=True, slots=True)
class TopicSelectionDecision:
    """Immutable, auditable result of bounded topic selection."""

    decision_id: UUID
    status: TopicDecisionStatus
    selected_candidate_id: UUID | None
    selected_topic: str | None
    candidate_ids: tuple[UUID, ...] = ()
    selected_score: TopicScore | None = None
    rationale: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status is TopicDecisionStatus.SELECTED:
            if self.selected_candidate_id is None or not self.selected_topic:
                raise ValueError("selected decisions require a candidate and topic")
            if self.selected_score is None:
                raise ValueError("selected decisions require a score")
            if self.selected_score.candidate_id != self.selected_candidate_id:
                raise ValueError("selected score must belong to the selected candidate")
            if self.selected_candidate_id not in self.candidate_ids:
                raise ValueError("selected candidate must be present in candidate_ids")
        elif self.status is TopicDecisionStatus.NO_SELECTION:
            if self.selected_candidate_id is not None or self.selected_topic is not None:
                raise ValueError("no-selection decisions cannot select a topic")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("candidate_ids must be unique")
        if any(not item.strip() for item in self.rationale):
            raise ValueError("decision rationale entries must not be blank")

    @classmethod
    def no_selection(
        cls,
        *,
        candidate_ids: tuple[UUID, ...] = (),
        rationale: tuple[str, ...] = (),
        decision_id: UUID | None = None,
    ) -> TopicSelectionDecision:
        return cls(
            decision_id=decision_id or uuid4(),
            status=TopicDecisionStatus.NO_SELECTION,
            selected_candidate_id=None,
            selected_topic=None,
            candidate_ids=candidate_ids,
            rationale=rationale,
        )
