from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class StockMediaSearchRequest:
    run_id: str
    request_id: str
    query: str
    operation: str = "search_photos"
    page: int = 1
    per_page: int = 15
    orientation: str | None = None
    provider_candidates: tuple[str, ...] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StockMediaSearchResult:
    provider: str
    query: str
    items: list[dict[str, Any]]
    total_results: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StockMediaStrategy:
    name: str
    query: str
    min_items: int = 1
    operation: str = "search_photos"
    orientation: str | None = "portrait"
    min_relevance: float = 0.20


class StockMediaGateway(Protocol):
    async def search(self, request: StockMediaSearchRequest) -> StockMediaSearchResult: ...
