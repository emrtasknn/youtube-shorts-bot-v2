from __future__ import annotations

import pytest

from app.application.ports.stock_media import (
    StockMediaSearchRequest,
    StockMediaSearchResult,
)
from app.application.services.stock_media_scoring import StockMediaScorer
from app.application.services.stock_media_selector import StockMediaSelector
from app.application.services.stock_media_strategy import StockMediaStrategyBuilder
from app.application.use_cases.search_stock_media import SearchStockMedia


class FakeStockMediaGateway:
    def __init__(self, results: dict[str, StockMediaSearchResult]) -> None:
        self.results = results
        self.requests: list[StockMediaSearchRequest] = []

    async def search(self, request: StockMediaSearchRequest) -> StockMediaSearchResult:
        self.requests.append(request)
        return self.results[request.query]


@pytest.mark.asyncio
async def test_strategy_fallback_continues_after_unusable_exact_results() -> None:
    gateway = FakeStockMediaGateway(
        {
            "strasbourg dancing plague 1518": StockMediaSearchResult(
                provider="pexels",
                query="strasbourg dancing plague 1518",
                items=[
                    {
                        "id": "exact-bad",
                        "type": "photo",
                        "width": 2160,
                        "height": 3840,
                        "alt": "generic crowd",
                    }
                ],
                total_results=1,
            ),
            "strasbourg old town": StockMediaSearchResult(
                provider="pexels",
                query="strasbourg old town",
                items=[
                    {
                        "id": "broader-good",
                        "type": "photo",
                        "width": 2160,
                        "height": 3840,
                        "alt": "Strasbourg old town historic street",
                    }
                ],
                total_results=1,
            ),
        }
    )
    strategies = StockMediaStrategyBuilder().build(
        exact_query="strasbourg dancing plague 1518",
        broader_queries=["strasbourg old town"],
    )

    result, selected = await SearchStockMedia(gateway).execute_strategy_until_selected(
        run_id="run-1",
        request_id="scene-1",
        strategies=strategies,
        selector=StockMediaSelector(StockMediaScorer()),
    )

    assert result.query == "strasbourg old town"
    assert selected.item["id"] == "broader-good"
    assert [request.query for request in gateway.requests] == [
        "strasbourg dancing plague 1518",
        "strasbourg old town",
    ]


@pytest.mark.asyncio
async def test_strategy_failure_contains_quality_diagnostics() -> None:
    gateway = FakeStockMediaGateway(
        {
            "specific": StockMediaSearchResult(
                provider="pexels",
                query="specific",
                items=[
                    {
                        "id": "bad",
                        "type": "photo",
                        "width": 3840,
                        "height": 2160,
                        "alt": "unrelated landscape",
                    }
                ],
                total_results=1,
            )
        }
    )

    with pytest.raises(RuntimeError, match="not_portrait"):
        await SearchStockMedia(gateway).execute_strategy_until_selected(
            run_id="run-2",
            request_id="scene-2",
            strategies=StockMediaStrategyBuilder().build(exact_query="specific"),
            selector=StockMediaSelector(StockMediaScorer()),
        )


@pytest.mark.asyncio
async def test_strategy_propagates_provider_candidates() -> None:
    gateway = FakeStockMediaGateway(
        {
            "specific": StockMediaSearchResult(
                provider="pexels",
                query="specific",
                items=[
                    {
                        "id": "good",
                        "type": "photo",
                        "width": 2160,
                        "height": 3840,
                        "alt": "specific",
                    }
                ],
                total_results=1,
            )
        }
    )
    strategies = StockMediaStrategyBuilder().build(
        exact_query="specific",
        provider_candidates=("pexels", "pixabay"),
    )

    await SearchStockMedia(gateway).execute_strategy_until_selected(
        run_id="run-3",
        request_id="scene-3",
        strategies=strategies,
        selector=StockMediaSelector(StockMediaScorer()),
    )

    assert gateway.requests[0].provider_candidates == ("pexels", "pixabay")
