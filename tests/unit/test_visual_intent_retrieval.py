import pytest

from app.application.ports.stock_media import (
    StockMediaSearchRequest,
    StockMediaSearchResult,
    StockMediaStrategy,
)
from app.application.services.stock_media_scoring import StockMediaScorer
from app.application.services.stock_media_selector import StockMediaSelector
from app.application.services.visual_decision import VisualDecision
from app.application.services.visual_intent import (
    VisualBeatType,
    VisualIntent,
    VisualSourcePriority,
)
from app.application.use_cases.search_stock_media import SearchStockMedia


class FakeGateway:
    async def search(self, request: StockMediaSearchRequest) -> StockMediaSearchResult:
        return StockMediaSearchResult(
            provider="fake",
            query=request.query,
            items=[
                {
                    "id": "jolson",
                    "alt": "Al Jolson performing The Jazz Singer in 1927",
                    "description": "Historical performance",
                    "title": "Al Jolson The Jazz Singer",
                    "width": 1080,
                    "height": 1920,
                }
            ],
            total_results=1,
        )


def _intent() -> VisualIntent:
    return VisualIntent(
        scene_index=0,
        primary_entity="Al Jolson",
        secondary_entities=("The Jazz Singer",),
        action="performing",
        location="Hollywood",
        era="1927",
        event="event",
        visual_goal="Show Al Jolson performing in The Jazz Singer.",
        must_show=("Al Jolson", "The Jazz Singer"),
        must_avoid=(),
        source_priority=VisualSourcePriority.EXACT_EVENT,
        beat_type=VisualBeatType.ACTION,
        specificity=0.75,
        confidence=0.90,
    )


@pytest.mark.asyncio
async def test_execute_visual_intent_returns_evidence() -> None:
    use_case = SearchStockMedia(FakeGateway())
    result, selection = await use_case.execute_visual_intent(
        run_id="run-1",
        request_id="req-1",
        strategies=[
            StockMediaStrategy(
                name="exact",
                query="Al Jolson The Jazz Singer 1927",
            )
        ],
        intent=_intent(),
        selector=StockMediaSelector(StockMediaScorer()),
    )

    assert result.provider == "fake"
    assert selection.item["id"] == "jolson"
    assert selection.evidence.decision == VisualDecision.ACCEPT_EXACT
    assert selection.evidence.source_is_exact is True
    assert "al" in selection.evidence.matched_terms
