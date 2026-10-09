from __future__ import annotations

import asyncio
import base64
import random
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.application.services.provider_performance_learning import (
    ProviderPerformanceLearning,
    ProviderPerformanceObservation,
)
from app.infrastructure.providers.contracts import (
    ErrorCategory,
    ProviderError,
    ProviderResult,
    ProviderUsage,
)


class RetryDecision(StrEnum):
    RETRY = "RETRY"
    FAIL = "FAIL"
    FALLBACK = "FALLBACK"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    jitter_ratio: float = 0.25


class RetryManager:
    def __init__(
        self,
        policy: RetryPolicy | None = None,
        sleep: Callable[[float], object] | None = None,
        random_fn: Callable[[], float] | None = None,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self._sleep = sleep or asyncio.sleep
        self._random = random_fn or random.random

    def classify(self, error: ProviderError) -> RetryDecision:
        if error.category in {
            ErrorCategory.TRANSIENT,
            ErrorCategory.RATE_LIMITED,
            ErrorCategory.TIMEOUT,
        }:
            return RetryDecision.RETRY
        if error.category == ErrorCategory.QUOTA_EXHAUSTED:
            return RetryDecision.FALLBACK
        return RetryDecision.FAIL

    def delay(self, attempt: int, error: ProviderError) -> float:
        if error.retry_after_seconds is not None:
            return float(max(0.0, min(error.retry_after_seconds, self.policy.max_delay_seconds)))
        exponential = self.policy.base_delay_seconds * (2 ** max(0, attempt - 1))
        bounded = min(exponential, self.policy.max_delay_seconds)
        jitter = bounded * self.policy.jitter_ratio * self._random()
        return float(min(self.policy.max_delay_seconds, bounded + jitter))

    async def wait(self, attempt: int, error: ProviderError) -> float:
        delay = self.delay(attempt, error)
        result = self._sleep(delay)
        if hasattr(result, "__await__"):
            await result
        return delay


class RateLimitExceeded(ProviderError):
    def __init__(self, provider: str, retry_after_seconds: float) -> None:
        super().__init__(
            code="RATE_LIMIT",
            category=ErrorCategory.RATE_LIMITED,
            provider=provider,
            message="Local provider rate limit exceeded",
            retryable=True,
            retry_after_seconds=retry_after_seconds,
        )


class TokenBucket:
    def __init__(self, rate_per_second: float, capacity: int) -> None:
        if rate_per_second <= 0 or capacity <= 0:
            raise ValueError("rate_per_second and capacity must be positive")
        self.rate = rate_per_second
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> float:
        if tokens <= 0:
            raise ValueError("tokens must be positive")
        async with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated_at) * self.rate)
                self.updated_at = now
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return 0.0
                wait_for = (tokens - self.tokens) / self.rate
                await asyncio.sleep(wait_for)


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}

    def configure(self, key: str, rate_per_second: float, capacity: int) -> None:
        self._buckets[key] = TokenBucket(rate_per_second, capacity)

    async def acquire(self, key: str, tokens: float = 1.0) -> float:
        bucket = self._buckets.get(key)
        if bucket is None:
            return 0.0
        return await bucket.acquire(tokens)


class ConcurrencyLimiter:
    def __init__(self) -> None:
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    def configure(self, key: str, limit: int) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        self._semaphores[key] = asyncio.Semaphore(limit)

    def semaphore(self, key: str) -> asyncio.Semaphore | _UnlimitedSemaphore:
        semaphore = self._semaphores.get(key)
        return semaphore if semaphore is not None else _UnlimitedSemaphore()


class _UnlimitedSemaphore:
    async def __aenter__(self) -> _UnlimitedSemaphore:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class QuotaExceeded(ProviderError):
    def __init__(self, provider: str, key: str) -> None:
        super().__init__(
            code="QUOTA_EXHAUSTED",
            category=ErrorCategory.QUOTA_EXHAUSTED,
            provider=provider,
            message=f"Quota exhausted: {key}",
            retryable=False,
        )


class QuotaManager:
    def __init__(self) -> None:
        self._limits: dict[str, float] = {}
        self._usage: dict[str, float] = defaultdict(float)

    def configure(self, key: str, limit: float) -> None:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        self._limits[key] = limit
        self._usage.setdefault(key, 0.0)

    def remaining(self, key: str) -> float | None:
        if key not in self._limits:
            return None
        return max(0.0, self._limits[key] - self._usage[key])

    def reserve(self, key: str, amount: float = 1.0, provider: str = "unknown") -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        remaining = self.remaining(key)
        if remaining is not None and amount > remaining:
            raise QuotaExceeded(provider, key)
        self._usage[key] += amount

    def release(self, key: str, amount: float = 1.0) -> None:
        self._usage[key] = max(0.0, self._usage[key] - amount)


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpen(ProviderError):
    def __init__(self, provider: str, retry_after_seconds: float) -> None:
        super().__init__(
            code="CIRCUIT_OPEN",
            category=ErrorCategory.TRANSIENT,
            provider=provider,
            message="Provider circuit is open",
            retryable=True,
            retry_after_seconds=retry_after_seconds,
        )


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_seconds: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if failure_threshold <= 0 or recovery_seconds <= 0:
            raise ValueError("failure_threshold and recovery_seconds must be positive")
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._clock = clock or time.monotonic
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.opened_at: float | None = None
        self._half_open_probe = False

    def allow_request(self, provider: str) -> None:
        if self.state == CircuitState.CLOSED:
            return
        if self.state == CircuitState.OPEN:
            assert self.opened_at is not None
            elapsed = self._clock() - self.opened_at
            if elapsed < self.recovery_seconds:
                raise CircuitOpen(provider, self.recovery_seconds - elapsed)
            self.state = CircuitState.HALF_OPEN
            self._half_open_probe = False
        if self.state == CircuitState.HALF_OPEN:
            if self._half_open_probe:
                raise CircuitOpen(provider, self.recovery_seconds)
            self._half_open_probe = True

    def record_success(self) -> None:
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.opened_at = None
        self._half_open_probe = False

    def record_failure(self) -> None:
        self.failures += 1
        if self.state == CircuitState.HALF_OPEN or self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.opened_at = self._clock()
            self._half_open_probe = False


class ProviderHealthManager:
    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def configure(
        self, provider: str, failure_threshold: int = 3, recovery_seconds: float = 30.0
    ) -> None:
        self._breakers[provider] = CircuitBreaker(failure_threshold, recovery_seconds)

    def breaker(self, provider: str) -> CircuitBreaker:
        return self._breakers.setdefault(provider, CircuitBreaker())

    def allow(self, provider: str) -> None:
        self.breaker(provider).allow_request(provider)

    def record_success(self, provider: str) -> None:
        self.breaker(provider).record_success()

    def record_failure(self, provider: str) -> None:
        self.breaker(provider).record_failure()


class FallbackExhausted(ProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="FALLBACK_EXHAUSTED",
            category=ErrorCategory.PERMANENT,
            provider="router",
            message=message,
        )


class StrategyRouter:
    def __init__(
        self,
        health: ProviderHealthManager,
        *,
        performance_learning: ProviderPerformanceLearning | None = None,
    ) -> None:
        self.health = health
        self.performance_learning = performance_learning

    def route(
        self,
        providers: list[str],
        attempted: set[str] | None = None,
        *,
        observations: tuple[ProviderPerformanceObservation, ...] = (),
        capability: str | None = None,
        operation: str | None = None,
    ) -> str:
        attempted = attempted or set()
        eligible: list[str] = []
        for provider in providers:
            if provider in attempted:
                continue
            try:
                self.health.allow(provider)
            except ProviderError:
                continue
            eligible.append(provider)

        if not eligible:
            raise FallbackExhausted("No eligible provider remains")

        if self.performance_learning is None or not observations:
            return eligible[0]

        learned = self.performance_learning.learn(
            observations,
            capability=capability,
            operation=operation,
        )
        ranked = sorted(
            enumerate(eligible),
            key=lambda item: (
                -self.performance_learning.ranking_score(item[1], learned=learned),
                item[0],
            ),
        )
        return ranked[0][1]


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    key: str
    result: ProviderResult
    created_at: datetime


class IdempotencyStore:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._records: dict[str, IdempotencyRecord] = {}

    def get(self, key: str, now: datetime | None = None) -> ProviderResult | None:
        record = self._records.get(key)
        if record is None:
            return None
        now = now or datetime.now(UTC)
        if now - record.created_at > timedelta(seconds=self.ttl_seconds):
            del self._records[key]
            return None
        return record.result

    def put(self, key: str, result: ProviderResult, now: datetime | None = None) -> None:
        self._records[key] = IdempotencyRecord(key, result, now or datetime.now(UTC))


_BYTES_MARKER = "__youtube_shorts_bot_bytes__"


def _json_safe(value: object) -> object:
    if isinstance(value, bytes):
        return {_BYTES_MARKER: base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _json_restore(value: object) -> object:
    if isinstance(value, dict):
        if set(value) == {_BYTES_MARKER} and isinstance(value[_BYTES_MARKER], str):
            return base64.b64decode(value[_BYTES_MARKER])
        return {str(key): _json_restore(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_restore(item) for item in value]
    return value


class DatabaseIdempotencyStore:
    """Durable idempotency store backed by PostgreSQL."""

    def __init__(self, session: Session, ttl_seconds: int = 3600) -> None:
        self.session = session
        self.ttl_seconds = ttl_seconds

    def get(self, key: str, now: datetime | None = None) -> ProviderResult | None:
        from app.infrastructure.database.models import ProviderIdempotencyModel

        now = now or datetime.now(UTC)
        record = self.session.scalar(
            select(ProviderIdempotencyModel).where(ProviderIdempotencyModel.idempotency_key == key)
        )
        if record is None:
            return None
        if now > record.expires_at:
            self.session.execute(
                delete(ProviderIdempotencyModel).where(ProviderIdempotencyModel.id == record.id)
            )
            self.session.commit()
            return None
        usage = record.usage or {}
        return ProviderResult(
            success=record.success,
            provider=record.provider,
            request_id=record.request_id,
            output=_json_restore(record.output) if record.output is not None else None,
            usage=ProviderUsage(
                input_units=int(usage.get("input_units", 0)),
                output_units=int(usage.get("output_units", 0)),
                total_units=int(usage.get("total_units", 0)),
            ),
            cost=Decimal(record.cost),
            latency_ms=record.latency_ms,
            metadata=record.result_metadata or {},
        )

    def put(self, key: str, result: ProviderResult, now: datetime | None = None) -> None:
        from app.infrastructure.database.models import ProviderIdempotencyModel

        now = now or datetime.now(UTC)
        values = {
            "idempotency_key": key,
            "provider": result.provider,
            "request_id": result.request_id,
            "success": result.success,
            "output": _json_safe(result.output),
            "usage": {
                "input_units": result.usage.input_units,
                "output_units": result.usage.output_units,
                "total_units": result.usage.total_units,
            },
            "cost": result.cost,
            "latency_ms": result.latency_ms,
            "metadata": result.metadata,
            "created_at": now,
            "expires_at": now + timedelta(seconds=self.ttl_seconds),
        }
        statement = insert(ProviderIdempotencyModel).values(**values)
        statement = statement.on_conflict_do_nothing(index_elements=["idempotency_key"])
        self.session.execute(statement)
        self.session.commit()


@dataclass(frozen=True, slots=True)
class CostRecord:
    provider: str
    operation: str
    amount: Decimal
    currency: str = "USD"


class CostBudgetExceeded(RuntimeError):
    """Raised when a run has exhausted its persisted budget."""


class CostTracker:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._records: list[CostRecord] = []

    def record(
        self,
        provider: str,
        operation: str,
        amount: Decimal,
        currency: str = "USD",
        run_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        self._records.append(CostRecord(provider, operation, amount, currency))
        if self._session is not None and run_id is not None:
            from app.infrastructure.database.models import CostEventModel

            self._session.add(
                CostEventModel(
                    run_id=UUID(run_id),
                    provider=provider,
                    operation=operation,
                    amount=amount,
                    currency=currency,
                    cost_metadata=metadata,
                )
            )
            self._session.commit()

    def budget_remaining(self, run_id: str, currency: str = "USD") -> Decimal | None:
        if self._session is None:
            return None
        from app.infrastructure.database.models import CostEventModel, RunModel

        run = self._session.get(RunModel, UUID(run_id))
        if run is None or run.budget_target is None:
            return None
        spent = self._session.scalar(
            select(func.coalesce(func.sum(CostEventModel.amount), 0)).where(
                CostEventModel.run_id == UUID(run_id),
                CostEventModel.currency == currency,
            )
        )
        return max(Decimal("0"), Decimal(run.budget_target) - Decimal(spent or 0))

    def ensure_budget(self, run_id: str, upcoming_cost: Decimal = Decimal("0")) -> None:
        if upcoming_cost < 0:
            raise ValueError("upcoming_cost must be non-negative")
        remaining = self.budget_remaining(run_id)
        if remaining is not None and (remaining <= 0 or upcoming_cost > remaining):
            raise CostBudgetExceeded(f"Run budget exhausted: remaining={remaining}")

    def total(self, currency: str = "USD") -> Decimal:
        return sum(
            (record.amount for record in self._records if record.currency == currency),
            Decimal("0"),
        )

    def records(self) -> tuple[CostRecord, ...]:
        return tuple(self._records)
