from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.provider_performance_learning import ProviderPerformanceObservation
from app.application.services.unified_optimization import ProviderCostObservation
from app.infrastructure.database.models import SystemEventModel


@dataclass(frozen=True, slots=True)
class ProductionProviderTelemetry:
    observations: tuple[ProviderPerformanceObservation, ...]
    costs: tuple[ProviderCostObservation, ...]


class ProductionProviderTelemetryStore:
    """Loads durable provider evidence emitted by ReliabilityTelemetry.

    System events are the source of truth. Learning remains derived and
    bounded; this store only reconstructs observations from persisted events.
    """

    _EVENT_TYPES = ("provider.success", "provider.error")

    def __init__(self, session: Session) -> None:
        self.session = session

    def load(
        self,
        *,
        capability: str | None = None,
        operation: str | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> ProductionProviderTelemetry:
        query = (
            select(SystemEventModel)
            .where(SystemEventModel.event_type.in_(self._EVENT_TYPES))
            .order_by(SystemEventModel.created_at.asc(), SystemEventModel.id.asc())
            .limit(limit)
        )
        if provider is not None:
            query = query.where(SystemEventModel.provider == provider)
        if since is not None:
            query = query.where(SystemEventModel.created_at >= since)

        events = tuple(self.session.scalars(query))
        observations: list[ProviderPerformanceObservation] = []
        costs: list[ProviderCostObservation] = []

        for sequence, event in enumerate(events, start=1):
            metadata = event.event_metadata or {}
            event_capability = _string(metadata.get("capability"))
            event_operation = _string(metadata.get("operation"))
            if capability is not None and event_capability != capability:
                continue
            if operation is not None and event_operation != operation:
                continue
            if not event.provider or not event_capability or not event_operation:
                continue

            success = event.event_type == "provider.success"
            latency = _non_negative_int(metadata.get("latency_ms"))
            quality = _quality_score(metadata.get("quality_score"))
            observations.append(
                ProviderPerformanceObservation(
                    sequence=sequence,
                    provider=event.provider,
                    capability=event_capability,
                    operation=event_operation,
                    success=success,
                    latency_ms=latency,
                    quality_score=quality,
                )
            )

            if success:
                cost = _non_negative_float(metadata.get("cost"))
                if cost is not None:
                    costs.append(
                        ProviderCostObservation(
                            sequence=sequence,
                            provider=event.provider,
                            capability=event_capability,
                            operation=event_operation,
                            cost=cost,
                        )
                    )

        return ProductionProviderTelemetry(
            observations=tuple(observations),
            costs=tuple(costs),
        )


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _non_negative_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) and value >= 0 else 0


def _non_negative_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return None


def _quality_score(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
