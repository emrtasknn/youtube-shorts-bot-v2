from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.application.services.event_memory import EventMemoryCandidate, EventMemoryService

NoveltyStatus = Literal["NEW", "DUPLICATE", "UNCERTAIN"]


@dataclass(frozen=True, slots=True)
class NoveltyDecision:
    status: NoveltyStatus
    accepted: bool
    reason: str
    matched_event_id: str | None = None


class NoveltyHardeningService:
    """Makes deterministic duplicate-event decisions from persistent memory."""

    def __init__(self, memory: EventMemoryService) -> None:
        self._memory = memory

    def evaluate(self, candidate: EventMemoryCandidate) -> NoveltyDecision:
        exact = self._memory.get(candidate.event_id)
        if exact is not None:
            return NoveltyDecision(
                status="DUPLICATE",
                accepted=False,
                reason="event_id_already_exists",
                matched_event_id=exact.event_id,
            )

        match = self._memory.find_match(candidate)
        if match is None:
            return NoveltyDecision(
                status="NEW",
                accepted=True,
                reason="no_strong_event_match",
            )

        if self._same_event_context(candidate, match):
            return NoveltyDecision(
                status="DUPLICATE",
                accepted=False,
                reason="strong_event_context_match",
                matched_event_id=match.event_id,
            )

        if not candidate.date and not candidate.location:
            return NoveltyDecision(
                status="DUPLICATE",
                accepted=False,
                reason="canonical_event_name_match",
                matched_event_id=match.event_id,
            )

        return NoveltyDecision(
            status="UNCERTAIN",
            accepted=True,
            reason="name_match_but_context_differs",
            matched_event_id=match.event_id,
        )

    @staticmethod
    def _same_event_context(
        candidate: EventMemoryCandidate,
        existing: EventMemoryCandidate,
    ) -> bool:
        if candidate.date and existing.date and candidate.date != existing.date:
            return False
        if (
            candidate.location
            and existing.location
            and candidate.location.casefold() != existing.location.casefold()
        ):
            return False

        candidate_entities = {value.casefold() for value in candidate.entities}
        existing_entities = {value.casefold() for value in existing.entities}
        if candidate_entities and existing_entities and candidate_entities & existing_entities:
            return True

        return (
            candidate.date is not None
            and existing.date is not None
            and candidate.location is not None
            and existing.location is not None
            and candidate.date == existing.date
            and candidate.location.casefold() == existing.location.casefold()
        )
