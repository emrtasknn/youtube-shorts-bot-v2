from __future__ import annotations

from app.application.ports.stock_media import (
    StockMediaGateway,
    StockMediaSearchRequest,
    StockMediaSearchResult,
    StockMediaStrategy,
)
from app.application.services.stock_media_selector import ScoredStockMedia, StockMediaSelector


class SearchStockMedia:
    def __init__(self, gateway: StockMediaGateway) -> None:
        self._gateway = gateway

    async def execute(self, request: StockMediaSearchRequest) -> StockMediaSearchResult:
        self._validate(request)
        return await self._gateway.search(request)

    async def execute_strategy(
        self,
        *,
        run_id: str,
        request_id: str,
        strategies: list[StockMediaStrategy],
        metadata: dict[str, object] | None = None,
    ) -> StockMediaSearchResult:
        if not strategies:
            raise ValueError("At least one stock media strategy is required")

        last_result: StockMediaSearchResult | None = None
        for strategy in strategies:
            result = await self.execute(
                StockMediaSearchRequest(
                    run_id=run_id,
                    request_id=f"{request_id}:{strategy.name}",
                    query=strategy.query,
                    operation=strategy.operation,
                    orientation=strategy.orientation,
                    provider_candidates=strategy.provider_candidates,
                    metadata={**(metadata or {}), "strategy": strategy.name},
                )
            )
            last_result = result
            if len(result.items) >= strategy.min_items:
                return result

        assert last_result is not None
        return last_result

    async def execute_strategy_until_selected(
        self,
        *,
        run_id: str,
        request_id: str,
        strategies: list[StockMediaStrategy],
        selector: StockMediaSelector,
        used_provider_asset_ids: set[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> tuple[StockMediaSearchResult, ScoredStockMedia]:
        if not strategies:
            raise ValueError("At least one stock media strategy is required")

        attempts: list[str] = []
        for strategy in strategies:
            result = await self.execute(
                StockMediaSearchRequest(
                    run_id=run_id,
                    request_id=f"{request_id}:{strategy.name}",
                    query=strategy.query,
                    operation=strategy.operation,
                    orientation=strategy.orientation,
                    metadata={**(metadata or {}), "strategy": strategy.name},
                )
            )
            ranked = selector.rank(
                result.items,
                query=strategy.query,
                used_provider_asset_ids=used_provider_asset_ids,
            )
            selected = selector.select(
                result.items,
                query=strategy.query,
                used_provider_asset_ids=used_provider_asset_ids,
                min_relevance=strategy.min_relevance,
            )
            if selected is not None:
                return result, selected

            best = ranked[0] if ranked else None
            if best is None:
                attempts.append(f"{strategy.name}:no_results")
            else:
                reasons = ",".join(best.score.reasons) or "below_threshold"
                attempts.append(
                    f"{strategy.name}:best={best.score.score:.3f}:"
                    f"relevance={best.score.relevance:.3f}:reasons={reasons}"
                )

        detail = "; ".join(attempts) or "no strategies executed"
        raise RuntimeError(f"No eligible stock asset found after strategy fallback: {detail}")

    @staticmethod
    def _validate(request: StockMediaSearchRequest) -> None:
        if not request.query.strip():
            raise ValueError("Stock media search query must not be empty")
        if request.operation not in {"search_photos", "search_videos"}:
            raise ValueError(f"Unsupported stock media operation: {request.operation}")
        if request.page < 1:
            raise ValueError("Stock media page must be at least 1")
        if not 1 <= request.per_page <= 80:
            raise ValueError("Stock media per_page must be between 1 and 80")
