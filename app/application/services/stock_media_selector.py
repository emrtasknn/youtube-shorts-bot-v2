from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.services.stock_media_scoring import StockMediaScore, StockMediaScorer


@dataclass(frozen=True, slots=True)
class ScoredStockMedia:
    item: dict[str, Any]
    score: StockMediaScore


class StockMediaSelector:
    def __init__(self, scorer: StockMediaScorer) -> None:
        self._scorer = scorer

    def select(
        self,
        items: list[dict[str, Any]],
        *,
        query: str,
        used_provider_asset_ids: set[str] | None = None,
        min_relevance: float = 0.20,
    ) -> ScoredStockMedia | None:
        ranked = self.rank(
            items,
            query=query,
            used_provider_asset_ids=used_provider_asset_ids,
        )
        eligible = [
            candidate
            for candidate in ranked
            if candidate.score.eligible and candidate.score.relevance >= min_relevance
        ]
        return eligible[0] if eligible else None

    def rank(
        self,
        items: list[dict[str, Any]],
        *,
        query: str,
        used_provider_asset_ids: set[str] | None = None,
        min_relevance: float = 0.20,
    ) -> list[ScoredStockMedia]:
        candidates = [
            ScoredStockMedia(
                item=item,
                score=self._scorer.score(
                    item,
                    query=query,
                    used_provider_asset_ids=used_provider_asset_ids,
                ),
            )
            for item in items
        ]
        return sorted(candidates, key=lambda candidate: candidate.score.score, reverse=True)
