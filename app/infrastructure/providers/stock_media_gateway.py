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
        registered = self._registry.candidates(ProviderCapability.STOCK_MEDIA)
        if not registered:
            raise RuntimeError("No enabled stock media provider is configured")

        if request.provider_candidates:
            by_name = {descriptor.name: descriptor for descriptor in registered}
            descriptors = [by_name[name] for name in request.provider_candidates if name in by_name]
            if not descriptors:
                raise RuntimeError(
                    "None of the requested stock media providers are enabled: "
                    + ", ".join(request.provider_candidates)
                )

            attempts: list[dict[str, object]] = []
            last_result = None
            for descriptor in descriptors:
                provider_request = self._build_request(
                    request,
                    provider=descriptor.name,
                    idempotency_key=(
                        f"stock-media:{request.run_id}:{request.request_id}:{descriptor.name}"
                    ),
                )
                result = await self._executor.execute(
                    provider_request,
                    candidates=[descriptor.name],
                )
                last_result = result
                output = result.output
                if not isinstance(output, dict):
                    raise RuntimeError("Stock media provider returned an invalid output")
                items = output.get("items", [])
                if not isinstance(items, list):
                    raise RuntimeError("Stock media provider returned invalid items")
                attempts.append({"provider": descriptor.name, "items": len(items)})
                if items:
                    return self._to_search_result(
                        request,
                        result,
                        items,
                        {
                            "provider_attempts": attempts,
                            "requested_provider_candidates": list(request.provider_candidates),
                        },
                    )

            assert last_result is not None
            output = last_result.output
            assert isinstance(output, dict)
            items = output.get("items", [])
            assert isinstance(items, list)
            return self._to_search_result(
                request,
                last_result,
                items,
                {
                    "provider_attempts": attempts,
                    "requested_provider_candidates": list(request.provider_candidates),
                },
            )

        provider_request = self._build_request(
            request,
            provider=registered[0].name,
            idempotency_key=f"stock-media:{request.run_id}:{request.request_id}",
        )
        result = await self._executor.execute(
            provider_request,
            candidates=[descriptor.name for descriptor in registered],
        )
        output = result.output
        if not isinstance(output, dict):
            raise RuntimeError("Stock media provider returned an invalid output")

        items = output.get("items", [])
        if not isinstance(items, list):
            raise RuntimeError("Stock media provider returned invalid items")

        return self._to_search_result(request, result, items, {})

    @staticmethod
    def _build_request(
        request: StockMediaSearchRequest,
        *,
        provider: str,
        idempotency_key: str,
    ) -> ProviderRequest:
        return ProviderRequest(
            request_id=request.request_id,
            run_id=request.run_id,
            capability=ProviderCapability.STOCK_MEDIA,
            operation=request.operation,
            provider=provider,
            payload={
                "query": request.query,
                "page": request.page,
                "per_page": request.per_page,
                "orientation": request.orientation,
            },
            idempotency_key=idempotency_key,
            metadata=request.metadata,
        )

    @staticmethod
    def _to_search_result(
        request: StockMediaSearchRequest,
        result,
        items: list[dict],
        extra_metadata: dict[str, object],
    ) -> StockMediaSearchResult:
        output = result.output
        assert isinstance(output, dict)
        return StockMediaSearchResult(
            provider=result.provider,
            query=request.query,
            items=items,
            total_results=int(output.get("total_results", 0)),
            metadata={
                **result.metadata,
                **extra_metadata,
                "request_id": result.request_id,
                "latency_ms": result.latency_ms,
            },
        )
