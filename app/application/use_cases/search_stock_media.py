from __future__ import annotations

from app.application.ports.stock_media import (
    StockMediaGateway,
    StockMediaSearchRequest,
    StockMediaSearchResult,
    StockMediaStrategy,
)
from app.application.services.stock_media_selector import ScoredStockMedia, StockMediaSelector
from app.application.services.visual_candidate_selector import (
    VisualCandidateSelection,
    VisualCandidateSelector,
)
from app.application.services.visual_intent import VisualIntent
from app.application.services.visual_relevance import VisualRelevanceContext


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
        relevance_context: VisualRelevanceContext | None = None,
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
                    provider_candidates=strategy.provider_candidates,
                    metadata={**(metadata or {}), "strategy": strategy.name},
                )
            )
            ranked = selector.rank(
                result.items,
                query=strategy.query,
                used_provider_asset_ids=used_provider_asset_ids,
                relevance_context=relevance_context,
            )
            selected = selector.select(
                result.items,
                query=strategy.query,
                used_provider_asset_ids=used_provider_asset_ids,
                min_relevance=strategy.min_relevance,
                relevance_context=relevance_context,
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

    async def execute_visual_intent(
        self,
        *,
        run_id: str,
        request_id: str,
        strategies: list[StockMediaStrategy],
        intent: VisualIntent,
        selector: StockMediaSelector,
        used_provider_asset_ids: set[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> tuple[StockMediaSearchResult, VisualCandidateSelection]:
        if not strategies:
            raise ValueError("At least one stock media strategy is required")

        evidence_selector = VisualCandidateSelector()
        context = VisualRelevanceContext(
            entities=(intent.primary_entity, *intent.secondary_entities),
            location=intent.location,
            era=intent.era,
            visual_goal=intent.visual_goal,
            action=intent.action,
            must_show=intent.must_show,
            must_avoid=intent.must_avoid,
        )

        attempts: list[str] = []
        for strategy in strategies:
            result = await self.execute(
                StockMediaSearchRequest(
                    run_id=run_id,
                    request_id=f"{request_id}:{strategy.name}",
                    query=strategy.query,
                    operation=strategy.operation,
                    orientation=strategy.orientation,
                    provider_candidates=strategy.provider_candidates,
                    metadata={
                        **(metadata or {}),
                        "strategy": strategy.name,
                        "visual_intent_scene_index": intent.scene_index,
                    },
                )
            )
            ranked = selector.rank(
                result.items,
                query=strategy.query,
                used_provider_asset_ids=used_provider_asset_ids,
                min_relevance=strategy.min_relevance,
                relevance_context=context,
            )
            candidates = [
                (candidate.item, candidate.score)
                for candidate in ranked
                if candidate.score.relevance >= strategy.min_relevance
                and candidate.score.duplicate_penalty == 0.0
            ]
            selected = evidence_selector.select(
                candidates,
                intent=intent,
                source_is_exact=strategy.name == "exact",
            )
            if selected is not None:
                return result, selected

            best = ranked[0] if ranked else None
            if best is None:
                attempts.append(f"{strategy.name}:no_results")
            else:
                attempts.append(
                    f"{strategy.name}:best={best.score.score:.3f}:"
                    f"relevance={best.score.relevance:.3f}"
                )

        detail = "; ".join(attempts) or "no strategies executed"
        raise RuntimeError(
            "No safe visual candidate found after evidence-aware retrieval: "
            f"{detail}"
        )

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
