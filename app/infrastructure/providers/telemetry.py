from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.enums import EventSeverity


@dataclass(frozen=True, slots=True)
class ReliabilityEvent:
    event_type: str
    severity: EventSeverity
    provider: str | None = None
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ReliabilityTelemetry:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._events: list[ReliabilityEvent] = []

    def emit(
        self,
        event_type: str,
        severity: EventSeverity,
        provider: str | None = None,
        message: str = "",
        metadata: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> ReliabilityEvent:
        event = ReliabilityEvent(
            event_type=event_type,
            severity=severity,
            provider=provider,
            message=message,
            metadata=metadata or {},
        )
        self._events.append(event)
        if self._session is not None and run_id is not None:
            from app.infrastructure.database.models import SystemEventModel

            try:
                self._session.add(
                    SystemEventModel(
                        run_id=UUID(run_id),
                        event_type=event_type,
                        severity=severity,
                        provider=provider,
                        message=message,
                        event_metadata=metadata or {},
                    )
                )
                self._session.commit()
            except (SQLAlchemyError, ValueError):
                self._session.rollback()
        return event

    def events(self) -> tuple[ReliabilityEvent, ...]:
        return tuple(self._events)
