from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.services.stock_media_scoring import StockMediaScore
from app.application.services.stock_media_selector import ScoredStockMedia
from app.application.services.visual_query_expansion import VisualQueryVariant


@dataclass(frozen=True, slots=True)
class VisualCandidatePoolEntry:
    item: dict[str, Any]
    score: StockMediaScore
    query_names: tuple[str, ...]
    queries: tuple[str, ...]
    providers: tuple[str, ...]
    best_query_priority: int

    @property
    def asset_id(self) -> str:
        return str(self.item.get("id") or self.item.get("asset_id") or "")


class VisualCandidatePool:
    """Canonical bounded pool that merges candidates across query variants."""

    def __init__(self, *, max_candidates: int = 40) -> None:
        if max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        self._max_candidates = max_candidates
        self._entries: dict[str, VisualCandidatePoolEntry] = {}

    def add(
        self,
        candidates: list[ScoredStockMedia],
        *,
        query: VisualQueryVariant,
        provider: str,
    ) -> None:
        for candidate in candidates:
            asset_id = str(candidate.item.get("id") or candidate.item.get("asset_id") or "")
            if not asset_id:
                continue
            existing = self._entries.get(asset_id)
            if existing is None:
                self._entries[asset_id] = VisualCandidatePoolEntry(
                    item=dict(candidate.item),
                    score=candidate.score,
                    query_names=(query.name,),
                    queries=(query.query,),
                    providers=(provider,),
                    best_query_priority=query.priority,
                )
                continue

            best_score = max(existing.score, candidate.score, key=lambda score: score.score)
            self._entries[asset_id] = VisualCandidatePoolEntry(
                item=existing.item,
                score=best_score,
                query_names=tuple(dict.fromkeys((*existing.query_names, query.name))),
                queries=tuple(dict.fromkeys((*existing.queries, query.query))),
                providers=tuple(dict.fromkeys((*existing.providers, provider))),
                best_query_priority=max(existing.best_query_priority, query.priority),
            )

        self._trim()

    def ranked(self) -> list[VisualCandidatePoolEntry]:
        return sorted(
            self._entries.values(),
            key=lambda entry: (
                entry.score.score,
                entry.score.relevance,
                entry.best_query_priority,
            ),
            reverse=True,
        )

    def __len__(self) -> int:
        return len(self._entries)

    def _trim(self) -> None:
        ranked = self.ranked()[: self._max_candidates]
        self._entries = {entry.asset_id: entry for entry in ranked}
