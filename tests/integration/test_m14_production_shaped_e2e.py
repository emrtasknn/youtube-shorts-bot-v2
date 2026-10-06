from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.domain.enums import ContentCategory, EventSeverity, RunStatus, RunType
from app.infrastructure.database.connection import get_session
from app.infrastructure.database.models import ContentModel, CostEventModel, ProviderIdempotencyModel, RunModel, SystemEventModel
from app.infrastructure.providers.contracts import ProviderCapability, ProviderRequest, ProviderResult
from app.infrastructure.providers.executor import ReliabilityExecutor
from app.infrastructure.providers.registry import ProviderRegistry
from app.infrastructure.providers.reliability import ConcurrencyLimiter, CostTracker, DatabaseIdempotencyStore, ProviderHealthManager, QuotaManager, RateLimiter, RetryManager, RetryPolicy, StrategyRouter
from app.infrastructure.providers.telemetry import ReliabilityTelemetry


class FakeTextProvider:
    name = "fake-text"
    capabilities = frozenset({ProviderCapability.TEXT_GENERATION})

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        self.calls += 1
        return ProviderResult(True, self.name, request.request_id, {"text": "deterministic result"}, cost=Decimal("0.0100"))


@pytest.mark.asyncio
async def test_production_shaped_provider_path_is_durable_and_idempotent() -> None:
    session = get_session()
    try:
        run_id = uuid4()
        content = ContentModel(content_key=f"e2e-content-{run_id}", language="en", category=ContentCategory.CUSTOM, topic="Production-shaped E2E")
        session.add(content)
        session.flush()
        session.add(RunModel(id=run_id, run_key=f"e2e-run-{run_id}", content_id=content.id, run_type=RunType.CUSTOM, status=RunStatus.RUNNING, language="en"))
        session.flush()
        provider = FakeTextProvider()
        registry = ProviderRegistry()
        registry.register(provider)
        health = ProviderHealthManager()
        health.configure(provider.name)
        executor = ReliabilityExecutor(registry=registry, retry=RetryManager(RetryPolicy(max_attempts=1)), health=health, rate_limiter=RateLimiter(), concurrency=ConcurrencyLimiter(), quota=QuotaManager(), idempotency=DatabaseIdempotencyStore(session), costs=CostTracker(session), router=StrategyRouter(health), telemetry=ReliabilityTelemetry(session))
        request = ProviderRequest(request_id="e2e-request", run_id=str(run_id), capability=ProviderCapability.TEXT_GENERATION, operation="generate_script", provider=provider.name, idempotency_key="e2e-idempotency-key", max_attempts=1)
        first = await executor.execute(request)
        second = await executor.execute(request)
        assert first == second
        assert provider.calls == 1
        cost_count = session.scalar(select(func.count()).select_from(CostEventModel).where(CostEventModel.run_id == run_id))
        idempotency_count = session.scalar(select(func.count()).select_from(ProviderIdempotencyModel).where(ProviderIdempotencyModel.idempotency_key == "e2e-idempotency-key"))
        events = session.scalars(select(SystemEventModel).where(SystemEventModel.run_id == run_id).order_by(SystemEventModel.created_at)).all()
        assert cost_count == 1
        assert idempotency_count == 1
        assert [event.event_type for event in events] == ["provider.success", "provider.idempotency_hit"]
        assert all(event.severity == EventSeverity.INFO for event in events)
    finally:
        session.close()
