from datetime import UTC, datetime
from uuid import uuid4

from app.infrastructure.providers.production_telemetry import ProductionProviderTelemetryStore


class _ScalarResult:
    def __init__(self, events):
        self._events = events

    def __iter__(self):
        return iter(self._events)


class _Session:
    def __init__(self, events):
        self.events = events

    def scalars(self, query):
        return _ScalarResult(self.events)


class _Event:
    def __init__(self, event_type, provider, metadata, created_at=None):
        self.id = uuid4()
        self.event_type = event_type
        self.provider = provider
        self.event_metadata = metadata
        self.created_at = created_at or datetime.now(UTC)


def test_store_reconstructs_performance_and_cost_evidence():
    events = [
        _Event(
            "provider.success",
            "fast",
            {
                "capability": "IMAGE_SEARCH",
                "operation": "search",
                "latency_ms": 120,
                "quality_score": 92.0,
                "cost": 0.02,
            },
        ),
        _Event(
            "provider.error",
            "fast",
            {
                "capability": "IMAGE_SEARCH",
                "operation": "search",
                "latency_ms": 0,
            },
        ),
    ]
    telemetry = ProductionProviderTelemetryStore(_Session(events)).load(
        capability="IMAGE_SEARCH",
        operation="search",
    )
    assert len(telemetry.observations) == 2
    assert telemetry.observations[0].success is True
    assert telemetry.observations[0].latency_ms == 120
    assert telemetry.observations[0].quality_score == 92.0
    assert telemetry.costs[0].cost == 0.02


def test_store_filters_provider_and_ignores_incomplete_events():
    events = [
        _Event("provider.success", "fast", {"capability": "TTS", "operation": "synthesize", "cost": 1}),
        _Event("provider.success", "slow", {"capability": "IMAGE_SEARCH", "operation": "search", "cost": 1}),
    ]
    telemetry = ProductionProviderTelemetryStore(_Session(events)).load(
        capability="IMAGE_SEARCH",
        operation="search",
        provider="slow",
    )
    assert [item.provider for item in telemetry.observations] == ["slow"]
    assert [item.provider for item in telemetry.costs] == ["slow"]
