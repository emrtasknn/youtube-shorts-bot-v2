from __future__ import annotations

from app.application.ports.stock_media import (
    StockMediaGateway,
    StockMediaSearchRequest,
    StockMediaSearchResult,
)
from app.infrastructure.providers.contracts import ProviderCapability, ProviderRequest
from app.infrastructure.providers.executor import ReliabilityExecutor
from app.infrastructure.providers.registry import ProviderRegistry


class ReliableStockMediaGateway(StockMediaGateway):
    def __init__(
        self,
        registry: ProviderRegistry,
        executor: ReliabilityExecutor,
    ) -> None:
        self._registry = registry
        self._executor = executor

    async def search(self, request: StockMediaSearchRequest) -> StockMediaSearchResult:
        descriptors = self._registry.candidates(ProviderCapability.STOCK_MEDIA)
        if not descriptors:
            raise RuntimeError("No enabled stock media provider is configured")

        provider_request = ProviderRequest(
            request_id=request.request_id,
            run_id=request.run_id,
            capability=ProviderCapability.STOCK_MEDIA,
            operation=request.operation,
            provider=descriptors[0].name,
            payload={
                "query": request.query,
                "page": request.page,
                "per_page": request.per_page,
                "orientation": request.orientation,
            },
            idempotency_key=f"stock-media:{request.run_id}:{request.request_id}",
            metadata=request.metadata,
        )
        result = await self._executor.execute(
            provider_request,
            candidates=[descriptor.name for descriptor in descriptors],
        )
        output = result.output
        if not isinstance(output, dict):
            raise RuntimeError("Stock media provider returned an invalid output")

        items = output.get("items", [])
        if not isinstance(items, list):
            raise RuntimeError("Stock media provider returned invalid items")

        return StockMediaSearchResult(
            provider=result.provider,
            query=request.query,
            items=items,
            total_results=int(output.get("total_results", 0)),
            metadata={
                **result.metadata,
                "request_id": result.request_id,
                "latency_ms": result.latency_ms,
            },
        )
