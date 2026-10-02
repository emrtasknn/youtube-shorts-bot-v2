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
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StockMediaSearchResult:
    provider: str
    query: str
    items: list[dict[str, Any]]
    total_results: int
    metadata: dict[str, Any] = field(default_factory=dict)


class StockMediaGateway(Protocol):
    async def search(self, request: StockMediaSearchRequest) -> StockMediaSearchResult: ...
