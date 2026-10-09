from app.application.services.stock_media_scoring import StockMediaScorer


def test_scorer_can_accept_high_resolution_archive_photo_with_portrait_crop() -> None:
    item = {
        "id": "commons:42",
        "type": "photo",
        "width": 2400,
        "height": 1600,
        "alt": "Chernobyl Reactor 4 archival photograph from 1986",
        "portrait_crop_allowed": True,
    }

    result = StockMediaScorer().score(
        item,
        query="Chernobyl Reactor 4",
        min_relevance=0.10,
    )

    assert result.eligible is True
    assert "portrait_crop_required" in result.reasons


def test_scorer_still_rejects_landscape_stock_without_crop_permission() -> None:
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
