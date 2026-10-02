import pytest

from app.application.ports.stock_media import (
    StockMediaSearchRequest,
    StockMediaSearchResult,
)
from app.application.use_cases.search_stock_media import SearchStockMedia


class FakeGateway:
    async def search(self, request: StockMediaSearchRequest) -> StockMediaSearchResult:
        return StockMediaSearchResult(
            provider="fake",
            query=request.query,
            items=[{"id": 1}],
            total_results=1,
        )


@pytest.mark.asyncio
async def test_search_stock_media_delegates_valid_request() -> None:
    result = await SearchStockMedia(FakeGateway()).execute(
        StockMediaSearchRequest(
            run_id="run-1",
            request_id="req-1",
            query="ancient roman ruins",
        )
    )

    assert result.provider == "fake"
    assert result.items == [{"id": 1}]


@pytest.mark.asyncio
async def test_search_stock_media_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match="query must not be empty"):
        await SearchStockMedia(FakeGateway()).execute(
            StockMediaSearchRequest(
                run_id="run-1",
                request_id="req-1",
                query=" ",
            )
        )
