from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import EventMemoryModel

EventMemoryStatus = Literal["NEW_EVENT", "KNOWN_EVENT", "UNCERTAIN", "USED"]
_ALLOWED_STATUSES = frozenset({"NEW_EVENT", "KNOWN_EVENT", "UNCERTAIN", "USED"})


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_list(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, list | tuple):
        raise ValueError("Event memory list fields must be lists")
    return tuple(normalized for item in values if (normalized := str(item).strip()))


@dataclass(frozen=True, slots=True)
class EventMemoryCandidate:
    event_id: str
    canonical_title: str
    aliases: tuple[str, ...] = ()
    date: str | None = None
    location: str | None = None
    entities: tuple[str, ...] = ()
    event_summary: str | None = None
    core_facts: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    first_video_id: str | None = None
    status: EventMemoryStatus = "UNCERTAIN"

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, fallback_title: str) -> EventMemoryCandidate:
        canonical_title = str(payload.get("canonical_title") or fallback_title).strip()
        if not canonical_title:
            raise ValueError("Event memory canonical_title must not be empty")

        status = str(payload.get("status") or "UNCERTAIN").strip().upper()
        if status not in _ALLOWED_STATUSES:
            raise ValueError(f"Unsupported event memory status: {status}")

        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            event_id = cls.build_event_id(
                canonical_title=canonical_title,
                date=str(payload.get("date") or ""),
                location=str(payload.get("location") or ""),
            )

        return cls(
            event_id=event_id,
            canonical_title=canonical_title,
            aliases=_normalize_list(payload.get("aliases")),
            date=str(payload["date"]).strip() if payload.get("date") else None,
            location=str(payload["location"]).strip() if payload.get("location") else None,
            entities=_normalize_list(payload.get("entities")),
            event_summary=(
                str(payload["event_summary"]).strip() if payload.get("event_summary") else None
            ),
            core_facts=_normalize_list(payload.get("core_facts")),
            claims=_normalize_list(payload.get("claims")),
            sources=_normalize_list(payload.get("sources")),
            first_video_id=(
                str(payload["first_video_id"]).strip() if payload.get("first_video_id") else None
            ),
            status=status,  # type: ignore[arg-type]
        )

    @staticmethod
    def build_event_id(*, canonical_title: str, date: str, location: str) -> str:
        key = "|".join(_normalize_text(value) for value in (canonical_title, date, location))
        return f"evt_{sha256(key.encode('utf-8')).hexdigest()[:16]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "canonical_title": self.canonical_title,
            "aliases": list(self.aliases),
            "date": self.date,
            "location": self.location,
            "entities": list(self.entities),
            "event_summary": self.event_summary,
            "core_facts": list(self.core_facts),
            "claims": list(self.claims),
            "sources": list(self.sources),
            "first_video_id": self.first_video_id,
            "status": self.status,
        }


class EventMemoryService:
    """Persists and retrieves canonical historical-event memory."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, event_id: str) -> EventMemoryCandidate | None:
        model = self._session.get(EventMemoryModel, event_id)
        return self._to_candidate(model) if model is not None else None

    def list(self, *, limit: int = 100) -> tuple[EventMemoryCandidate, ...]:
        if limit <= 0:
            raise ValueError("Event memory limit must be positive")
        models = self._session.scalars(
            select(EventMemoryModel).order_by(EventMemoryModel.created_at.desc()).limit(limit)
        ).all()
        return tuple(self._to_candidate(model) for model in models)

    def find_match(self, candidate: EventMemoryCandidate) -> EventMemoryCandidate | None:
        target = {
            _normalize_text(candidate.canonical_title),
            *map(_normalize_text, candidate.aliases),
        }
        for existing in self.list(limit=500):
            existing_names = {
                _normalize_text(existing.canonical_title),
                *map(_normalize_text, existing.aliases),
            }
            if target & existing_names:
                return existing
        return None

    def upsert(self, candidate: EventMemoryCandidate) -> EventMemoryCandidate:
        existing = self.get(candidate.event_id)
        if existing is None:
            model = EventMemoryModel(
                event_id=candidate.event_id,
                canonical_title=candidate.canonical_title,
                aliases=list(candidate.aliases),
                event_date=candidate.date,
                location=candidate.location,
                entities=list(candidate.entities),
                event_summary=candidate.event_summary,
                core_facts=list(candidate.core_facts),
                claims=list(candidate.claims),
                sources=list(candidate.sources),
                first_video_id=candidate.first_video_id,
                status=candidate.status,
            )
            self._session.add(model)
            self._session.flush()
            return candidate

        stored_model = self._session.get(EventMemoryModel, candidate.event_id)
        assert stored_model is not None
        stored_model.aliases = sorted(set(existing.aliases) | set(candidate.aliases))
        stored_model.entities = sorted(set(existing.entities) | set(candidate.entities))
        stored_model.core_facts = sorted(set(existing.core_facts) | set(candidate.core_facts))
        stored_model.claims = sorted(set(existing.claims) | set(candidate.claims))
        stored_model.sources = sorted(set(existing.sources) | set(candidate.sources))
        stored_model.event_date = existing.date or candidate.date
        stored_model.location = existing.location or candidate.location
        stored_model.event_summary = existing.event_summary or candidate.event_summary
        stored_model.first_video_id = existing.first_video_id or candidate.first_video_id
        stored_model.status = "USED" if "USED" in {existing.status, candidate.status} else candidate.status
        self._session.flush()
        return self._to_candidate(stored_model)

    @staticmethod
    def _to_candidate(model: EventMemoryModel) -> EventMemoryCandidate:
        return EventMemoryCandidate(
            event_id=model.event_id,
            canonical_title=model.canonical_title,
            aliases=tuple(model.aliases or []),
            date=model.event_date,
            location=model.location,
            entities=tuple(model.entities or []),
            event_summary=model.event_summary,
            core_facts=tuple(model.core_facts or []),
            claims=tuple(model.claims or []),
            sources=tuple(model.sources or []),
            first_video_id=model.first_video_id,
            status=model.status,  # type: ignore[arg-type]
        )
