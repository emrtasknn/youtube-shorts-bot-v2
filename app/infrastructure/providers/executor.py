from __future__ import annotations

import sys
from dataclasses import dataclass
from time import perf_counter

from app.infrastructure.providers.contracts import ProviderError, ProviderRequest, ProviderResult
from app.infrastructure.providers.registry import ProviderRegistry
from app.infrastructure.providers.reliability import (
    ConcurrencyLimiter,
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

    async def execute(
        self,
        request: ProviderRequest,
        candidates: list[str] | None = None,
        quota_key: str | None = None,
    ) -> ProviderResult:
        key = request.idempotency_key
        if key:
            cached = self.idempotency.get(key)
            if cached is not None:
                return cached

        providers = candidates or [request.provider]
        attempted: set[str] = set()
        last_error: ProviderError | None = None

        while len(attempted) < len(providers):
            provider_name = self.router.route(providers, attempted)
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
                    decision = self.retry.classify(error)
                    if decision == RetryDecision.RETRY and attempt < request.max_attempts:
                        await self.retry.wait(attempt, error)
                        continue
                    break

        assert last_error is not None
        raise last_error
