from decimal import Decimal

import pytest

from app.application.ports.stock_media import StockMediaSearchRequest
from app.infrastructure.providers.contracts import ProviderCapability, ProviderResult
from app.infrastructure.providers.executor import ReliabilityExecutor
from app.infrastructure.providers.fakes import FakeProvider
from app.infrastructure.providers.registry import ProviderRegistry
from app.infrastructure.providers.reliability import (
    ConcurrencyLimiter,
    CostTracker,
    IdempotencyStore,
    ProviderHealthManager,
    QuotaManager,
    RateLimiter,
    RetryManager,
    RetryPolicy,
    StrategyRouter,
)
from app.infrastructure.providers.stock_media_gateway import ReliableStockMediaGateway


@pytest.mark.asyncio
async def test_stock_media_gateway_uses_registry_and_reliability() -> None:
    registry = ProviderRegistry()

    async def handler(request):
        return ProviderResult(
            success=True,
            provider=request.provider,
            request_id=request.request_id,
            output={
                "query": request.payload["query"],
                "items": [{"id": 123}],
                "total_results": 1,
            },
            cost=Decimal("0"),
        )

    provider = FakeProvider("pexels", frozenset({ProviderCapability.STOCK_MEDIA}), handler)
    registry.register(provider)

    health = ProviderHealthManager()
    health.configure("pexels", failure_threshold=2)
    executor = ReliabilityExecutor(
        registry=registry,
        retry=RetryManager(RetryPolicy(max_attempts=1)),
        health=health,
        rate_limiter=RateLimiter(),
        concurrency=ConcurrencyLimiter(),
        quota=QuotaManager(),
        idempotency=IdempotencyStore(),
        costs=CostTracker(),
        router=StrategyRouter(health),
    )

    result = await ReliableStockMediaGateway(registry, executor).search(
        StockMediaSearchRequest(
            run_id="run-1",
            request_id="req-1",
            query="roman ruins",
        )
    )

    assert result.provider == "pexels"
    assert result.items == [{"id": 123}]
    assert provider.calls == 1
