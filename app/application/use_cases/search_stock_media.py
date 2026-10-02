from __future__ import annotations

from app.application.ports.stock_media import (
    StockMediaGateway,
    StockMediaSearchRequest,
    StockMediaSearchResult,
    StockMediaStrategy,
)


class SearchStockMedia:
    def __init__(self, gateway: StockMediaGateway) -> None:
        self._gateway = gateway

    async def execute(self, request: StockMediaSearchRequest) -> StockMediaSearchResult:
        self._validate(request)
        return await self._gateway.search(request)

    async def execute_strategy(
        self,
        *,
        run_id: str,
        request_id: str,
        strategies: list[StockMediaStrategy],
        metadata: dict[str, object] | None = None,
    ) -> StockMediaSearchResult:
        if not strategies:
            raise ValueError("At least one stock media strategy is required")

        last_result: StockMediaSearchResult | None = None
        for strategy in strategies:
            result = await self.execute(
                StockMediaSearchRequest(
                    run_id=run_id,
                    request_id=f"{request_id}:{strategy.name}",
                    query=strategy.query,
                    operation=strategy.operation,
                    orientation=strategy.orientation,
                    metadata={**(metadata or {}), "strategy": strategy.name},
                )
            )
            last_result = result
            if len(result.items) >= strategy.min_items:
                return result

        assert last_result is not None
        return last_result

    @staticmethod
    def _validate(request: StockMediaSearchRequest) -> None:
        if not request.query.strip():
            raise ValueError("Stock media search query must not be empty")
        if request.operation not in {"search_photos", "search_videos"}:
            raise ValueError(f"Unsupported stock media operation: {request.operation}")
        if request.page < 1:
            raise ValueError("Stock media page must be at least 1")
        if not 1 <= request.per_page <= 80:
            raise ValueError("Stock media per_page must be between 1 and 80")
