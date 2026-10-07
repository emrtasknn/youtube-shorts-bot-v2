from unittest.mock import AsyncMock, Mock

import pytest

from app.application.services.scene_contract import build_scene_contract
from app.application.services.stock_media_scoring import StockMediaScore
from app.application.services.visual_beat import VisualBeatCompiler
from app.application.services.visual_beat_retriever import VisualBeatRetriever
from app.application.services.visual_semantic_verification import (
    VisualSemanticScore,
    VisualVerificationDecision,
    VisualVerificationResult,
)


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
    retriever._semantic_verifier = Mock()
    retriever._semantic_verifier.verify.return_value = _verification(
        VisualVerificationDecision.ACCEPT
    )

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
    assert result.verification_decision == "accept"
    assert result.semantic_verification_score == 0.9
    assert result.semantic_verifier == "test-verifier"
    search.execute_strategy.assert_awaited_once()
    kwargs = search.execute_strategy.await_args.kwargs
    assert kwargs["strategies"][0].name == "exact"
    rank_kwargs = retriever._selector.rank.call_args.kwargs
    assert rank_kwargs["relevance_context"].entities == beat.entities
    assert rank_kwargs["relevance_context"].location == beat.location
    assert rank_kwargs["relevance_context"].era == beat.era


def _verification(decision: VisualVerificationDecision) -> VisualVerificationResult:
    return VisualVerificationResult(
        decision=decision,
        score=VisualSemanticScore(
            entity_match=1.0,
            action_match=1.0,
            context_match=1.0,
            must_show_match=1.0,
            must_avoid_compliance=1.0,
            overall=0.9 if decision == VisualVerificationDecision.ACCEPT else 0.5,
        ),
        verifier="test-verifier",
        matched_signals=("roman empire",),
    )


def _build_beat():
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
    return (
        VisualBeatCompiler()
        .compile(
            scene,
            scene_index=0,
            scene_duration_seconds=4.0,
        )
        .beats[0]
    )


def _candidate(asset_id: str):
    candidate = Mock()
    candidate.item = {"id": asset_id, "download_url": f"https://example.test/{asset_id}.jpg"}
    candidate.score = StockMediaScore(
        score=0.9,
        relevance=0.95,
        orientation=1.0,
        resolution=0.8,
        duration=1.0,
        duplicate_penalty=0.0,
        eligible=True,
        reasons=(),
    )
    return candidate


@pytest.mark.asyncio
async def test_visual_beat_retriever_retries_after_m19_rejection() -> None:
    search = Mock()
    search.execute_strategy = AsyncMock(
        return_value=Mock(provider="pexels", query="Roman Empire expansion", items=[{}])
    )
    retriever = VisualBeatRetriever(Mock())
    retriever._search = search
    first = _candidate("rejected")
    second = _candidate("accepted")
    retriever._selector = Mock()
    retriever._selector.rank.return_value = [first, second]
    retriever._semantic_verifier = Mock()
    retriever._semantic_verifier.verify.return_value = _verification(
        VisualVerificationDecision.ACCEPT
    )

    rejected = Mock()
    rejected.decision.value = "reject"
    rejected.score.overall = 0.2
    rejected.score.beautifiable = False
    accepted = Mock()
    accepted.decision.value = "accept"
    accepted.score.overall = 0.9
    accepted.score.beautifiable = False
    retriever._quality_evaluator = Mock()
    retriever._quality_evaluator.evaluate.side_effect = [rejected, accepted]

    result = await retriever.retrieve(
        run_id="run-1",
        request_id="request-1",
        beat=_build_beat(),
    )

    assert result.item["id"] == "accepted"
    assert result.quality_decision == "accept"
    assert retriever._quality_evaluator.evaluate.call_count == 2


@pytest.mark.asyncio
async def test_visual_beat_retriever_falls_through_to_broader_strategy() -> None:
    search = Mock()
    search.execute_strategy = AsyncMock(
        side_effect=[
            Mock(provider="pexels", query="exact", items=[{}]),
            Mock(provider="pexels", query="broader", items=[{}]),
        ]
    )
    retriever = VisualBeatRetriever(Mock())
    retriever._search = search
    rejected_candidate = _candidate("exact-rejected")
    accepted_candidate = _candidate("broader-accepted")
    retriever._selector = Mock()
    retriever._selector.rank.side_effect = [[rejected_candidate], [accepted_candidate]]
    retriever._semantic_verifier = Mock()
    retriever._semantic_verifier.verify.return_value = _verification(
        VisualVerificationDecision.ACCEPT
    )

    rejected = Mock()
    rejected.decision.value = "reject"
    rejected.score.overall = 0.2
    rejected.score.beautifiable = False
    accepted = Mock()
    accepted.decision.value = "accept"
    accepted.score.overall = 0.9
    accepted.score.beautifiable = False
    retriever._quality_evaluator = Mock()
    retriever._quality_evaluator.evaluate.side_effect = [rejected, accepted]

    result = await retriever.retrieve(
        run_id="run-1",
        request_id="request-1",
        beat=_build_beat(),
    )

    assert result.item["id"] == "broader-accepted"
    assert search.execute_strategy.await_count == 2
    assert (
        search.execute_strategy.await_args_list[1]
        .kwargs["strategies"][0]
        .name.startswith("broader_")
    )


@pytest.mark.asyncio
async def test_visual_beat_retriever_raises_when_all_candidates_fail_quality() -> None:
    search = Mock()
    search.execute_strategy = AsyncMock(
        return_value=Mock(provider="pexels", query="Roman Empire expansion", items=[{}])
    )
    retriever = VisualBeatRetriever(Mock())
    retriever._search = search
    candidate = _candidate("rejected")
    retriever._selector = Mock()
    retriever._selector.rank.return_value = [candidate]
    retriever._semantic_verifier = Mock()
    retriever._semantic_verifier.verify.return_value = _verification(
        VisualVerificationDecision.REJECT
    )

    rejected = Mock()
    rejected.decision.value = "reject"
    rejected.score.overall = 0.2
    rejected.score.beautifiable = False
    retriever._quality_evaluator = Mock()
    retriever._quality_evaluator.evaluate.return_value = rejected

    with pytest.raises(RuntimeError, match="verification gates"):
        await retriever.retrieve(
            run_id="run-1",
            request_id="request-1",
            beat=_build_beat(),
        )


@pytest.mark.asyncio
async def test_visual_beat_retriever_retries_after_m20_uncertain() -> None:
    search = Mock()
    search.execute_strategy = AsyncMock(
        return_value=Mock(provider="pexels", query="Roman Empire expansion", items=[{}])
    )
    retriever = VisualBeatRetriever(Mock())
    retriever._search = search
    first = _candidate("uncertain")
    second = _candidate("accepted")
    retriever._selector = Mock()
    retriever._selector.rank.return_value = [first, second]

    rejected = Mock()
    rejected.decision.value = "accept"
    rejected.score.overall = 0.9
    rejected.score.beautifiable = False
    accepted = Mock()
    accepted.decision.value = "accept"
    accepted.score.overall = 0.9
    accepted.score.beautifiable = False
    retriever._quality_evaluator = Mock()
    retriever._quality_evaluator.evaluate.side_effect = [rejected, accepted]
    retriever._semantic_verifier = Mock()
    retriever._semantic_verifier.verify.side_effect = [
        _verification(VisualVerificationDecision.UNCERTAIN),
        _verification(VisualVerificationDecision.ACCEPT),
    ]

    result = await retriever.retrieve(
        run_id="run-1",
        request_id="request-1",
        beat=_build_beat(),
    )

    assert result.item["id"] == "accepted"
    assert retriever._semantic_verifier.verify.call_count == 2


@pytest.mark.asyncio
async def test_visual_beat_retriever_accepts_degraded_m20_verification() -> None:
    search = Mock()
    search.execute_strategy = AsyncMock(
        return_value=Mock(provider="pexels", query="Roman Empire expansion", items=[{}])
    )
    retriever = VisualBeatRetriever(Mock())
    retriever._search = search
    candidate = _candidate("degraded")
    retriever._selector = Mock()
    retriever._selector.rank.return_value = [candidate]

    quality = Mock()
    quality.decision.value = "accept"
    quality.score.overall = 0.9
    quality.score.beautifiable = False
    retriever._quality_evaluator = Mock()
    retriever._quality_evaluator.evaluate.return_value = quality
    retriever._semantic_verifier = Mock()
    retriever._semantic_verifier.verify.return_value = _verification(
        VisualVerificationDecision.ACCEPT_DEGRADED
    )

    result = await retriever.retrieve(
        run_id="run-1",
        request_id="request-1",
        beat=_build_beat(),
    )

    assert result.item["id"] == "degraded"
    assert result.verification_decision == "accept_degraded"


@pytest.mark.asyncio
async def test_visual_beat_retriever_falls_back_after_search_provider_error() -> None:
    search = Mock()
    search.execute_strategy = AsyncMock(
        side_effect=[
            RuntimeError("provider unavailable"),
            Mock(provider="pexels", query="broader", items=[{}]),
        ]
    )
    retriever = VisualBeatRetriever(Mock())
    retriever._search = search
    candidate = _candidate("broader-accepted")
    retriever._selector = Mock()
    retriever._selector.rank.return_value = [candidate]
    quality = Mock()
    quality.decision.value = "accept"
    quality.score.overall = 0.9
    quality.score.beautifiable = False
    retriever._quality_evaluator = Mock()
    retriever._quality_evaluator.evaluate.return_value = quality
    retriever._semantic_verifier = Mock()
    retriever._semantic_verifier.verify.return_value = _verification(
        VisualVerificationDecision.ACCEPT
    )

    result = await retriever.retrieve(
        run_id="run-1",
        request_id="request-1",
        beat=_build_beat(),
    )

    assert result.item["id"] == "broader-accepted"
    assert search.execute_strategy.await_count == 2


@pytest.mark.asyncio
async def test_visual_beat_retriever_falls_back_after_semantic_verifier_error() -> None:
    search = Mock()
    search.execute_strategy = AsyncMock(
        return_value=Mock(
            provider="pexels",
            query="Roman Empire expansion",
            items=[{}],
        )
    )
    retriever = VisualBeatRetriever(Mock())
    retriever._search = search
    first = _candidate("verification-error")
    second = _candidate("accepted")
    retriever._selector = Mock()
    retriever._selector.rank.return_value = [first, second]
    quality = Mock()
    quality.decision.value = "accept"
    quality.score.overall = 0.9
    quality.score.beautifiable = False
    retriever._quality_evaluator = Mock()
    retriever._quality_evaluator.evaluate.return_value = quality
    retriever._semantic_verifier = Mock()
    retriever._semantic_verifier.verify.side_effect = [
        RuntimeError("vision provider timeout"),
        _verification(VisualVerificationDecision.ACCEPT),
    ]

    result = await retriever.retrieve(
        run_id="run-1",
        request_id="request-1",
        beat=_build_beat(),
    )

    assert result.item["id"] == "accepted"
    assert retriever._semantic_verifier.verify.call_count == 2
