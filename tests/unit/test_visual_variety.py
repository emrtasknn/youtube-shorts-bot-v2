from app.application.services.stock_media_scoring import StockMediaScore
from app.application.services.stock_media_selector import ScoredStockMedia
from app.application.services.visual_variety import VisualVarietyEngine


def _candidate(
    asset_id: str,
    *,
    provider: str,
    title: str,
    width: int = 1080,
    height: int = 1920,
) -> ScoredStockMedia:
    return ScoredStockMedia(
        item={
            "id": asset_id,
            "title": title,
            "width": width,
            "height": height,
            "_provider": provider,
        },
        score=StockMediaScore(
            score=0.90,
            relevance=0.95,
            orientation=1.0,
            resolution=1.0,
            duration=1.0,
            duplicate_penalty=0.0,
            eligible=True,
            reasons=(),
        ),
    )


def test_variety_prefers_new_provider_and_shot_type() -> None:
    engine = VisualVarietyEngine()
    previous = _candidate(
        "old",
        provider="pexels",
        title="Roman emperor portrait",
    )
    engine.remember(
        run_id="run-1",
        item=previous.item,
        provider="pexels",
        subject_terms=("Roman Empire",),
    )

    repeated = _candidate(
        "repeated",
        provider="pexels",
        title="Roman emperor portrait",
    )
    varied = _candidate(
        "varied",
        provider="pixabay",
        title="aerial wide landscape",
        width=1440,
        height=1920,
    )

    ranked = engine.rank(
        [repeated, varied],
        run_id="run-1",
        subject_terms=("Roman Empire",),
    )

    assert ranked[0].item["id"] == "varied"


def test_variety_blocks_exact_reuse_when_an_alternative_exists() -> None:
    engine = VisualVarietyEngine()
    item = _candidate(
        "same",
        provider="pexels",
        title="Roman Empire",
    ).item
    engine.remember(run_id="run-1", item=item, provider="pexels")

    ranked = engine.rank(
        [
            _candidate("same", provider="pexels", title="Roman Empire"),
            _candidate("new", provider="pexels", title="Roman Empire map"),
        ],
        run_id="run-1",
    )

    assert ranked[0].item["id"] == "new"


def test_variety_degrades_gracefully_with_empty_history() -> None:
    engine = VisualVarietyEngine()

    ranked = engine.rank(
        [_candidate("only", provider="pexels", title="Roman Empire")],
        run_id="run-1",
    )

    assert [candidate.item["id"] for candidate in ranked] == ["only"]
    assert engine.history_size("run-1") == 0


def test_variety_history_is_bounded() -> None:
    engine = VisualVarietyEngine(max_history=2)
    for index in range(4):
        candidate = _candidate(
            str(index),
            provider="pexels",
            title=f"history item {index}",
        )
        engine.remember(run_id="run-1", item=candidate.item, provider="pexels")

    assert engine.history_size("run-1") == 2
