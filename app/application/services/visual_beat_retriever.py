from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.ports.stock_media import StockMediaGateway, StockMediaStrategy
from app.application.services.scene_contract import SceneContract
from app.application.services.stock_media_quality import StockMediaQualityEvaluator
from app.application.services.stock_media_scoring import StockMediaScorer
from app.application.services.stock_media_selector import StockMediaSelector
from app.application.services.visual_beat import VisualBeat
from app.application.services.visual_beat_retrieval import to_visual_relevance_context
from app.application.services.visual_source_resolver import VisualSourceResolver
from app.application.use_cases.search_stock_media import SearchStockMedia


@dataclass(frozen=True, slots=True)
class VisualBeatRetrievalResult:
    beat: VisualBeat
    provider: str
    query: str
    item: dict[str, Any]
    score: float
    quality_decision: str
    visual_quality: float
    beautifiable: bool


class VisualBeatRetriever:
    """Retrieves assets for timed beats through the existing M17 retrieval path."""

    def __init__(self, gateway: StockMediaGateway) -> None:
        self._search = SearchStockMedia(gateway)
        self._selector = StockMediaSelector(StockMediaScorer())
        self._quality_evaluator = StockMediaQualityEvaluator()

    async def retrieve(
        self,
        *,
        run_id: str,
        request_id: str,
        beat: VisualBeat,
    ) -> VisualBeatRetrievalResult:
        scene = SceneContract(
            narration=beat.narration,
            visual_goal=beat.visual_goal,
            visual_query=beat.visual_query,
            purpose=beat.purpose,
            subject=beat.subject,
            action=beat.action,
            entities=beat.entities,
            location=beat.location,
            era=beat.era,
            visual_intent=beat.visual_intent,
            visual_style=beat.visual_style,
            must_show=beat.must_show,
            must_avoid=beat.must_avoid,
        )
        source_plan = VisualSourceResolver().resolve(scene)
        if source_plan.kind != "stock":
            raise RuntimeError(f"Unsupported visual source: {source_plan.kind}")

        strategies = [
            StockMediaStrategy(
                name="exact",
                query=source_plan.exact_query,
                operation="search_photos",
                orientation="portrait",
            ),
            *[
                StockMediaStrategy(
                    name=f"broader_{index}",
                    query=query,
                    operation="search_photos",
                    orientation="portrait",
                    min_relevance=0.10,
                )
                for index, query in enumerate(source_plan.broader_queries, start=1)
            ],
        ]
        relevance_context = to_visual_relevance_context(beat)
        attempts: list[str] = []
        for strategy in strategies:
            result = await self._search.execute_strategy(
                run_id=run_id,
                request_id=request_id,
                strategies=[strategy],
            )
            ranked = self._selector.rank(
                result.items,
                query=strategy.query,
                min_relevance=strategy.min_relevance,
                relevance_context=relevance_context,
            )
            eligible = [
                candidate
                for candidate in ranked
                if candidate.score.eligible and candidate.score.relevance >= strategy.min_relevance
            ]
            for candidate in eligible:
                quality_result = self._quality_evaluator.evaluate(candidate.score)
                if quality_result.decision.value == "reject":
                    continue
                return VisualBeatRetrievalResult(
                    beat=beat,
                    provider=result.provider,
                    query=result.query,
                    item=dict(candidate.item),
                    score=candidate.score.score,
                    quality_decision=quality_result.decision.value,
                    visual_quality=quality_result.score.overall,
                    beautifiable=quality_result.score.beautifiable,
                )
            attempts.append(
                f"{strategy.name}:quality_rejected={len(eligible)}"
                if eligible
                else f"{strategy.name}:no_semantically_eligible_candidates"
            )
        detail = "; ".join(attempts) or "no strategies executed"
        raise RuntimeError(
            "No stock asset passed semantic relevance and visual quality gates: " + detail
        )
