from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

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
    def __init__(self) -> None:
        self._events: list[ReliabilityEvent] = []

    def emit(
        self,
        event_type: str,
        severity: EventSeverity,
        provider: str | None = None,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ReliabilityEvent:
        event = ReliabilityEvent(
            event_type=event_type,
            severity=severity,
            provider=provider,
            message=message,
            metadata=metadata or {},
        )
        self._events.append(event)
        return event

    def events(self) -> tuple[ReliabilityEvent, ...]:
        return tuple(self._events)
