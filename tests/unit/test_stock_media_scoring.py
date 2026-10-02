from app.application.services.stock_media_scoring import StockMediaScorer
from app.application.services.stock_media_selector import StockMediaSelector


def test_scorer_prefers_relevant_portrait_high_resolution_media() -> None:
    item = {
        "id": "1",
        "type": "photo",
        "width": 2160,
        "height": 3840,
        "alt": "ancient roman forum ruins in Rome",
    }
    result = StockMediaScorer().score(item, query="roman forum")
    assert result.eligible is True
    assert result.score >= 0.60


def test_scorer_rejects_landscape_media() -> None:
    item = {
        "id": "2",
        "type": "photo",
        "width": 3840,
        "height": 2160,
        "alt": "ancient roman forum",
    }
    result = StockMediaScorer().score(item, query="roman forum")
    assert result.eligible is False
    assert "not_portrait" in result.reasons


def test_scorer_rejects_previously_used_asset() -> None:
    item = {
        "id": "3",
        "type": "photo",
        "width": 2160,
        "height": 3840,
        "alt": "ancient roman forum",
    }
    result = StockMediaScorer().score(
        item,
        query="roman forum",
        used_provider_asset_ids={"3"},
    )
    assert result.eligible is False
    assert "already_used" in result.reasons


def test_selector_returns_highest_scoring_eligible_candidate() -> None:
    items = [
        {
            "id": "low",
            "type": "photo",
            "width": 1080,
            "height": 1920,
            "alt": "old ruins",
        },
        {
            "id": "high",
            "type": "photo",
            "width": 2160,
            "height": 3840,
            "alt": "ancient roman forum ruins",
        },
    ]
    selected = StockMediaSelector(StockMediaScorer()).select(
        items,
        query="roman forum",
    )
    assert selected is not None
    assert selected.item["id"] == "high"
