from unittest.mock import AsyncMock, Mock

import pytest

from app.application.services.scene_contract import build_scene_contract
from app.application.services.visual_beat import VisualBeatCompiler
from app.application.services.visual_beat_retriever import VisualBeatRetriever


@pytest.mark.asyncio
async def test_visual_beat_retriever_routes_through_existing_m17_search() -> None:
    gateway = Mock()
    search = Mock()
    selected = Mock()
    selected.item = {"id": "asset-1", "download_url": "https://example.test/a.jpg"}
    selected.score.score = 0.91
    search.execute_strategy_until_selected = AsyncMock(
        return_value=(
            Mock(provider="pexels", query="Roman Empire expansion"),
            selected,
        )
    )

    retriever = VisualBeatRetriever(gateway)
    retriever._search = search

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
    beat = VisualBeatCompiler().compile(
        scene,
        scene_index=0,
        scene_duration_seconds=6.0,
    ).beats[0]

    result = await retriever.retrieve(
        run_id="run-1",
        request_id="run-1:scene:0:beat:0",
        beat=beat,
    )

    assert result.item["id"] == "asset-1"
    assert result.provider == "pexels"
    search.execute_strategy_until_selected.assert_awaited_once()
    kwargs = search.execute_strategy_until_selected.await_args.kwargs
    assert kwargs["relevance_context"].entities == beat.entities
    assert kwargs["relevance_context"].location == beat.location
    assert kwargs["relevance_context"].era == beat.era
