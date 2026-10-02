from __future__ import annotations

from app.application.ports.stock_media import (
    StockMediaGateway,
    StockMediaSearchRequest,
    StockMediaSearchResult,
)


class SearchStockMedia:
    def __init__(self, gateway: StockMediaGateway) -> None:
        self._gateway = gateway

    async def execute(self, request: StockMediaSearchRequest) -> StockMediaSearchResult:
        if not request.query.strip():
            raise ValueError("Stock media search query must not be empty")
        if request.operation not in {"search_photos", "search_videos"}:
            raise ValueError(f"Unsupported stock media operation: {request.operation}")
        if request.page < 1:
            raise ValueError("Stock media page must be at least 1")
        if not 1 <= request.per_page <= 80:
            raise ValueError("Stock media per_page must be between 1 and 80")
        return await self._gateway.search(request)
