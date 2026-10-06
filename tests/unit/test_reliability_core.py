from decimal import Decimal

import pytest

from app.domain.enums import EventSeverity
from app.infrastructure.providers.contracts import (
    ErrorCategory,
    ProviderCapability,
    ProviderError,
    ProviderRequest,
    ProviderResult,
)
from app.infrastructure.providers.executor import ReliabilityExecutor
from app.infrastructure.providers.fakes import FakeProvider, success_result
from app.infrastructure.providers.registry import ProviderDescriptor, ProviderRegistry
from app.infrastructure.providers.reliability import (
    CircuitOpen,
    CircuitState,
    CostTracker,
    IdempotencyStore,
    ProviderHealthManager,
    QuotaExceeded,
    QuotaManager,
    RateLimiter,
    RetryManager,
    RetryPolicy,
    StrategyRouter,
    _json_restore,
    _json_safe,
)
from app.infrastructure.providers.telemetry import ReliabilityTelemetry


def request(key: str = "key") -> ProviderRequest:
    return ProviderRequest(
        request_id="req-1",
        run_id="run-1",
        capability=ProviderCapability.TEXT_GENERATION,
        operation="generate",
        provider="primary",
        idempotency_key=key,
    )


def test_registry_orders_by_priority() -> None:
    registry = ProviderRegistry()
    for name, priority in [("secondary", 20), ("primary", 10)]:
        registry.register(
            FakeProvider(name, frozenset({ProviderCapability.TEXT_GENERATION}), success_result),
            ProviderDescriptor(name, frozenset({ProviderCapability.TEXT_GENERATION}), priority),
        )
    assert [d.name for d in registry.candidates(ProviderCapability.TEXT_GENERATION)] == [
        "primary",
        "secondary",
    ]


def test_retry_honors_retry_after() -> None:
    retry = RetryManager(RetryPolicy(max_delay_seconds=10), random_fn=lambda: 0.0)
    error = ProviderError(
        code="429",
        category=ErrorCategory.RATE_LIMITED,
        provider="primary",
        message="rate limited",
        retryable=True,
        retry_after_seconds=7,
    )
    assert retry.delay(1, error) == 7


def test_quota_blocks_before_exceeding_limit() -> None:
    quota = QuotaManager()
    quota.configure("daily", 2)
    quota.reserve("daily")
    quota.reserve("daily")
    with pytest.raises(QuotaExceeded):
        quota.reserve("daily", provider="primary")


def test_circuit_breaker_recovery() -> None:
    health = ProviderHealthManager()
    health.configure("primary", failure_threshold=1, recovery_seconds=1)
    breaker = health.breaker("primary")
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    with pytest.raises(CircuitOpen):
        breaker.allow_request("primary")


@pytest.mark.asyncio
async def test_executor_falls_back_after_primary_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = ProviderRegistry()

    async def fail(_: ProviderRequest) -> ProviderResult:
        raise ProviderError(
            code="503",
            category=ErrorCategory.TRANSIENT,
            provider="primary",
            message="down",
            retryable=True,
        )

    primary = FakeProvider("primary", frozenset({ProviderCapability.TEXT_GENERATION}), fail)
    secondary = FakeProvider(
        "secondary", frozenset({ProviderCapability.TEXT_GENERATION}), success_result
    )
    registry.register(primary)
    registry.register(secondary)
    health = ProviderHealthManager()
    health.configure("primary", failure_threshold=1)
    health.configure("secondary", failure_threshold=1)
    executor = ReliabilityExecutor(
        registry=registry,
        retry=RetryManager(RetryPolicy(max_attempts=1)),
        health=health,
        rate_limiter=RateLimiter(),
        concurrency=__import__(
            "app.infrastructure.providers.reliability", fromlist=["ConcurrencyLimiter"]
        ).ConcurrencyLimiter(),
        quota=QuotaManager(),
        idempotency=IdempotencyStore(),
        costs=CostTracker(),
        router=StrategyRouter(health),
    )
    result = await executor.execute(request(), candidates=["primary", "secondary"])
    captured = capsys.readouterr()
    assert result.provider == "secondary"
    assert primary.calls == 1
    assert secondary.calls == 1
    assert "[provider-fallback]" in captured.err
    assert captured.out == ""


def test_idempotency_returns_same_result() -> None:
    store = IdempotencyStore()
    result = ProviderResult(True, "primary", "req", "output", cost=Decimal("0.01"))
    store.put("same", result)
    assert store.get("same") == result


def test_telemetry_event() -> None:
    telemetry = ReliabilityTelemetry()
    event = telemetry.emit("PROVIDER_429", EventSeverity.WARNING, "primary")
    assert event.provider == "primary"
    assert len(telemetry.events()) == 1



def test_json_safe_round_trips_binary_provider_output() -> None:
    output = {
        "audio_bytes": b"\x00\x01binary-audio",
        "format": "mp3",
        "nested": [b"more-bytes"],
    }
    encoded = _json_safe(output)
    assert isinstance(encoded, dict)
    assert isinstance(encoded["audio_bytes"], dict)
    assert isinstance(encoded["nested"], list)
    assert _json_restore(encoded) == output
