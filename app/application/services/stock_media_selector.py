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
    ) -> ScoredStockMedia | None:
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
        eligible = [candidate for candidate in candidates if candidate.score.eligible]
        if not eligible:
            return None
        return max(eligible, key=lambda candidate: candidate.score.score)
