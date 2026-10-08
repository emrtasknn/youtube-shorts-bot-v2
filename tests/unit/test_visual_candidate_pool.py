from app.application.services.stock_media_scoring import StockMediaScore
from app.application.services.stock_media_selector import ScoredStockMedia
from app.application.services.visual_candidate_pool import VisualCandidatePool
from app.application.services.visual_query_expansion import VisualQueryVariant


def _candidate(asset_id: str, score: float) -> ScoredStockMedia:
    return ScoredStockMedia(
        item={"id": asset_id, "title": asset_id},
        score=StockMediaScore(
            score=score,
            relevance=score,
            orientation=1.0,
            resolution=1.0,
            duration=1.0,
            duplicate_penalty=0.0,
            eligible=True,
            reasons=(),
        ),
    )


def test_candidate_pool_deduplicates_and_merges_query_provider_trace() -> None:
    pool = VisualCandidatePool(max_candidates=10)
    first = VisualQueryVariant("primary", "Roman Empire", 100)
    second = VisualQueryVariant("entity_action", "Roman Empire expanding", 90)

    pool.add(
        [_candidate("asset-1", 0.80), _candidate("asset-2", 0.70)], query=first, provider="pexels"
    )
    pool.add([_candidate("asset-1", 0.92)], query=second, provider="pixabay")

    ranked = pool.ranked()

    assert len(pool) == 2
    assert ranked[0].asset_id == "asset-1"
    assert ranked[0].score.score == 0.92
    assert ranked[0].query_names == ("primary", "entity_action")
    assert ranked[0].queries == ("Roman Empire", "Roman Empire expanding")
    assert ranked[0].providers == ("pexels", "pixabay")


def test_candidate_pool_is_bounded_by_global_best_candidates() -> None:
    pool = VisualCandidatePool(max_candidates=2)
    query = VisualQueryVariant("primary", "history", 100)

    pool.add(
        [_candidate("asset-1", 0.40), _candidate("asset-2", 0.90), _candidate("asset-3", 0.80)],
        query=query,
        provider="pexels",
    )

    assert len(pool) == 2
    assert [entry.asset_id for entry in pool.ranked()] == ["asset-2", "asset-3"]
