from __future__ import annotations

from app.application.ports.stock_media import StockMediaStrategy


class StockMediaStrategyBuilder:
    def build(
        self,
        *,
        exact_query: str,
        broader_queries: list[str] | None = None,
        operation: str = "search_photos",
        orientation: str | None = "portrait",
        provider_candidates: tuple[str, ...] | None = None,
    ) -> list[StockMediaStrategy]:
        exact = exact_query.strip()
        if not exact:
            raise ValueError("Exact stock media query must not be empty")

        strategies = [
            StockMediaStrategy(
                name="exact",
                query=exact,
                operation=operation,
                orientation=orientation,
                provider_candidates=provider_candidates,
            )
        ]
        for index, query in enumerate(broader_queries or [], start=1):
            normalized = query.strip()
            if normalized and normalized != exact:
                strategies.append(
                    StockMediaStrategy(
                        name=f"broader_{index}",
                        query=normalized,
                        operation=operation,
                        orientation=orientation,
                        provider_candidates=provider_candidates,
                        min_relevance=0.10,
                    )
                )
        return strategies
