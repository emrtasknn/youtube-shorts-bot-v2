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
                    )
                )
        return strategies
