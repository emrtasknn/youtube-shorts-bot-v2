from unittest.mock import AsyncMock, Mock

import pytest

from app.application.services.scene_contract import build_scene_contract
from app.application.services.stock_media_scoring import StockMediaScore
from app.application.services.visual_beat import VisualBeatCompiler
from app.application.services.visual_beat_retriever import VisualBeatRetriever


def _beat():
    scene = build_scene_contract(
        {
            "narration": "Rome expanded across the Mediterranean.",
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
    return VisualBeatCompiler().compile(
        scene,
        scene_index=0,
        scene_duration_seconds=4.0,
    ).beats[0]


def _candidate(asset_id: str, metadata: dict[str, object]) -> Mock:
    candidate = Mock()
    candidate.item = {
        "id": asset_id,
        "download_url": f"https://example.test/{asset_id}.jpg",
        **metadata,
    }
    candidate.score = StockMediaScore(
        score=0.91,
        relevance=0.95,
        orientation=1.0,
        resolution=0.90,
        duration=1.0,
        duplicate_penalty=0.0,
        eligible=True,
        reasons=(),
    )
    return candidate


@pytest.mark.asyncio
async def test_visual_pipeline_rejects_wrong_visual_and_accepts_semantically_verified_candidate() -> None:
    search = Mock()
    search.execute_strategy = AsyncMock(
        return_value=Mock(
            provider="pexels",
            query="Roman Empire Mediterranean expansion",
            items=[{}, {}],
        )
    )

    retriever = VisualBeatRetriever(Mock())
    retriever._search = search

    wrong = _candidate(
        "wrong-visual",
        {
            "title": "Modern city skyline",
            "description": "A modern city with contemporary architecture.",
            "tags": ["modern borders", "city", "architecture"],
        },
    )
    correct = _candidate(
        "correct-visual",
        {
            "title": "Roman Empire expansion across Mediterranean",
            "description": "Roman territory expanding across the Mediterranean in ancient Rome.",
            "tags": ["Rome", "Roman Empire", "expanding", "Roman territory"],
        },
    )

    retriever._selector = Mock()
    retriever._selector.rank.return_value = [wrong, correct]

    result = await retriever.retrieve(
        run_id="run-1",
        request_id="run-1:scene:0:beat:0",
        beat=_beat(),
    )

    assert result.item["id"] == "correct-visual"
    assert result.quality_decision == "accept"
    assert result.visual_quality >= 0.75
    assert result.verification_decision == "accept"
    assert result.semantic_verification_score >= 0.78
    assert result.semantic_verifier == "deterministic-metadata-v1"
    assert "roman empire" in result.matched_signals
    assert "roman territory" in result.matched_signals
    assert result.violated_constraints == ()
    assert retriever._selector.rank.call_count == 1
