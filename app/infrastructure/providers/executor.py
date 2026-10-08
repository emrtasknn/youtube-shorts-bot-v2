from __future__ import annotations

import sys
from dataclasses import dataclass, field
from time import perf_counter

from app.domain.enums import EventSeverity
from app.application.services.provider_performance_learning import ProviderPerformanceObservation
from app.infrastructure.providers.contracts import ProviderError, ProviderRequest, ProviderResult
from app.infrastructure.providers.registry import ProviderRegistry
from app.infrastructure.providers.reliability import (
    ConcurrencyLimiter,
    CostBudgetExceeded,
    CostTracker,
    DatabaseIdempotencyStore,
    IdempotencyStore,
    ProviderHealthManager,
    QuotaManager,
    RateLimiter,
    RetryDecision,
    RetryManager,
    StrategyRouter,
)
from app.infrastructure.providers.telemetry import ReliabilityTelemetry
from app.infrastructure.providers.production_telemetry import ProductionProviderTelemetryStore


@dataclass(slots=True)
class ReliabilityExecutor:
    registry: ProviderRegistry
    retry: RetryManager
    health: ProviderHealthManager
    rate_limiter: RateLimiter
    concurrency: ConcurrencyLimiter
    quota: QuotaManager
    idempotency: IdempotencyStore | DatabaseIdempotencyStore
    costs: CostTracker
    router: StrategyRouter
    telemetry: ReliabilityTelemetry = field(default_factory=ReliabilityTelemetry)
    production_telemetry: ProductionProviderTelemetryStore | None = None

    async def execute(
        self,
        request: ProviderRequest,
        candidates: list[str] | None = None,
        quota_key: str | None = None,
        historical_performance: tuple[ProviderPerformanceObservation, ...] = (),
    ) -> ProviderResult:
        key = request.idempotency_key
        if key:
            cached = self.idempotency.get(key)
            if cached is not None:
                self.telemetry.emit(
                    "provider.idempotency_hit",
                    EventSeverity.INFO,
                    provider=cached.provider,
                    message="Provider result served from idempotency store",
                    metadata={"request_id": cached.request_id},
                    run_id=request.run_id,
                )
                return cached

        providers = candidates or [request.provider]
        attempted: set[str] = set()
        last_error: ProviderError | None = None
        performance_history: list[ProviderPerformanceObservation] = list(historical_performance)
        if self.production_telemetry is not None:
            durable = self.production_telemetry.load(
                capability=request.capability.value,
                operation=request.operation,
            )
            performance_history = list(durable.observations) + performance_history

        while len(attempted) < len(providers):
            provider_name = self.router.route(
                providers,
                attempted,
                observations=tuple(performance_history),
                capability=request.capability.value,
                operation=request.operation,
            )
            attempted.add(provider_name)
            if len(attempted) > 1:
                # CLI stdout is a machine-readable JSON contract. Keep
                # failover diagnostics explicitly on stderr so shell
                # consumers cannot accidentally parse them as JSON.
                print(
                    "[provider-fallback] "
                    f"capability={request.capability.value} "
                    f"operation={request.operation} provider={provider_name}",
                    file=sys.stderr,
                    flush=True,
                )
            provider_request = ProviderRequest(
                request_id=request.request_id,
                run_id=request.run_id,
                capability=request.capability,
                operation=request.operation,
                provider=provider_name,
                payload=request.payload,
                model=request.model,
                idempotency_key=key,
                timeout_seconds=request.timeout_seconds,
                max_attempts=request.max_attempts,
                metadata=request.metadata,
            )
            adapter = self.registry.get(provider_name)

            try:
                self.costs.ensure_budget(request.run_id)
            except CostBudgetExceeded as error:
                self.telemetry.emit(
                    "provider.budget_exhausted",
                    EventSeverity.ERROR,
                    provider=provider_name,
                    message=str(error),
                    metadata={"request_id": request.request_id},
                    run_id=request.run_id,
                )
                raise

            for attempt in range(1, min(request.max_attempts, self.retry.policy.max_attempts) + 1):
                try:
                    self.health.allow(provider_name)
                    await self.rate_limiter.acquire(provider_name)
                    if quota_key:
                        self.quota.reserve(quota_key, provider=provider_name)
                    started = perf_counter()
                    async with self.concurrency.semaphore(provider_name):
                        result = await adapter.execute(provider_request)
                    latency_ms = int((perf_counter() - started) * 1000)
                    result = ProviderResult(
                        success=result.success,
                        provider=result.provider,
                        request_id=result.request_id,
                        output=result.output,
                        usage=result.usage,
                        cost=result.cost,
                        latency_ms=latency_ms,
                        metadata=result.metadata,
                    )
                    self.health.record_success(provider_name)
                    performance_history.append(
                        ProviderPerformanceObservation(
                            sequence=len(performance_history) + 1,
                            provider=provider_name,
                            capability=request.capability.value,
                            operation=request.operation,
                            success=result.success,
                            latency_ms=latency_ms,
                            quality_score=_quality_score(result.metadata),
                        )
                    )
                    self.telemetry.emit(
                        "provider.success",
                        EventSeverity.INFO,
                        provider=provider_name,
                        message="Provider request succeeded",
                        metadata={
                            "request_id": request.request_id,
                            "attempt": attempt,
                            "latency_ms": latency_ms,
                            "cost": float(result.cost),
                            "quality_score": _quality_score(result.metadata),
                            "capability": request.capability.value,
                            "operation": request.operation,
                        },
                        run_id=request.run_id,
                    )
                    self.costs.record(
                        provider_name,
                        request.operation,
                        result.cost,
                        run_id=request.run_id,
                        metadata={
                            "request_id": request.request_id,
                            "capability": request.capability.value,
                        },
                    )
                    if key:
                        self.idempotency.put(key, result)
                    return result
                except ProviderError as error:
                    last_error = error
                    self.health.record_failure(provider_name)
                    performance_history.append(
                        ProviderPerformanceObservation(
                            sequence=len(performance_history) + 1,
                            provider=provider_name,
                            capability=request.capability.value,
                            operation=request.operation,
                            success=False,
                            latency_ms=0,
                            quality_score=None,
                        )
                    )
                    self.telemetry.emit(
                        "provider.error",
                        EventSeverity.WARNING if error.retryable else EventSeverity.ERROR,
                        provider=provider_name,
                        message=str(error),
                        metadata={
                            "request_id": request.request_id,
                            "attempt": attempt,
                            "error_code": error.code,
                            "capability": request.capability.value,
                            "operation": request.operation,
                            "latency_ms": 0,
                            "category": error.category.value,
                        },
                        run_id=request.run_id,
                    )
                    decision = self.retry.classify(error)
                    if decision == RetryDecision.RETRY and attempt < request.max_attempts:
                        await self.retry.wait(attempt, error)
                        continue
                    break

        assert last_error is not None
        self.telemetry.emit(
            "provider.exhausted",
            EventSeverity.ERROR,
            provider=last_error.provider,
            message="Provider execution exhausted all eligible attempts",
            metadata={"request_id": request.request_id, "error_code": last_error.code},
            run_id=request.run_id,
        )
        raise last_error


def _quality_score(metadata: dict[str, object]) -> float | None:
    value = metadata.get("quality_score")
    if isinstance(value, (int, float)):
        return float(value)
    return None
