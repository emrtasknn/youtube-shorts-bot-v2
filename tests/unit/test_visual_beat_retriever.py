from unittest.mock import AsyncMock, Mock

import pytest

from app.application.services.scene_contract import build_scene_contract
from app.application.services.stock_media_scoring import StockMediaScore
from app.application.services.visual_beat import VisualBeatCompiler
from app.application.services.visual_beat_retriever import VisualBeatRetriever


@pytest.mark.asyncio
async def test_visual_beat_retriever_routes_through_existing_m17_search() -> None:
    gateway = Mock()
    search = Mock()
    selected = Mock()
    selected.item = {"id": "asset-1", "download_url": "https://example.test/a.jpg"}
    selected.score = StockMediaScore(
        score=0.91,
        relevance=0.95,
        orientation=1.0,
        resolution=0.70,
        duration=1.0,
        duplicate_penalty=0.0,
        eligible=True,
        reasons=(),
    )
    search.execute_strategy = AsyncMock(
        return_value=Mock(
            provider="pexels",
            query="Roman Empire expansion",
            items=[selected.item],
        )
    )

    retriever = VisualBeatRetriever(gateway)
    retriever._search = search
    retriever._selector = Mock()
    retriever._selector.rank.return_value = [selected]

    scene = build_scene_contract(
        {
            "narration": "Rome expanded across the Mediterranean. Its armies secured key ports.",
            "visual_goal": "Show Roman expansion",
            "visual_query": "Roman Empire Mediterranean expansion",
            "purpose": "event",
            "subject": "Roman Empire",
            "action": "expanding",
            "entities": ["Rome", "Roman Empire"],
            "location": "Mediterranean",
            "era": "ancient Rome",
            "visual_intent": "territorial expansion",
            "visual_style": "documentary",
            "must_show": ["Roman territory"],
            "must_avoid": ["modern borders"],
        }
    )
    beat = (
        VisualBeatCompiler()
        .compile(
            scene,
            scene_index=0,
            scene_duration_seconds=6.0,
        )
        .beats[0]
    )

    result = await retriever.retrieve(
        run_id="run-1",
        request_id="run-1:scene:0:beat:0",
        beat=beat,
    )

    assert result.item["id"] == "asset-1"
    assert result.provider == "pexels"
    assert result.quality_decision == "accept"
    assert result.visual_quality == 0.865
    assert result.beautifiable is False
    search.execute_strategy.assert_awaited_once()
    kwargs = search.execute_strategy.await_args.kwargs
    assert kwargs["strategies"][0].name == "exact"
    rank_kwargs = retriever._selector.rank.call_args.kwargs
    assert rank_kwargs["relevance_context"].entities == beat.entities
    assert rank_kwargs["relevance_context"].location == beat.location
    assert rank_kwargs["relevance_context"].era == beat.era
