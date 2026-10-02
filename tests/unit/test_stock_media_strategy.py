import pytest

from app.application.services.stock_media_strategy import StockMediaStrategyBuilder


def test_strategy_builder_keeps_exact_query_first() -> None:
    strategies = StockMediaStrategyBuilder().build(
        exact_query="roman forum",
        broader_queries=["ancient roman ruins", "history ruins"],
    )
    assert [strategy.name for strategy in strategies] == ["exact", "broader_1", "broader_2"]


def test_strategy_builder_rejects_empty_exact_query() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        StockMediaStrategyBuilder().build(exact_query=" ")
