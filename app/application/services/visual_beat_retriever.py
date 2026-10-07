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
from app.application.services.visual_semantic_verifier import (
    DeterministicVisualSemanticVerifier,
    VisualSemanticVerifier,
    VisualVerificationContext,
    to_visual_verification_context,
)
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
    verification_decision: str
    semantic_verification_score: float
    semantic_verifier: str
    matched_signals: tuple[str, ...]
    missing_signals: tuple[str, ...]
    violated_constraints: tuple[str, ...]
    retrieval_attempts: tuple[str, ...]


class VisualBeatRetriever:
    """Retrieves assets for timed beats through the existing M17 retrieval path."""

    def __init__(
        self,
        gateway: StockMediaGateway,
        *,
        semantic_verifier: VisualSemanticVerifier | None = None,
    ) -> None:
        self._search = SearchStockMedia(gateway)
        self._selector = StockMediaSelector(StockMediaScorer())
        self._quality_evaluator = StockMediaQualityEvaluator()
        self._semantic_verifier = semantic_verifier or DeterministicVisualSemanticVerifier()

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
        verification_context: VisualVerificationContext = to_visual_verification_context(beat)
        attempts: list[str] = []
        for strategy in strategies:
            try:
                result = await self._search.execute_strategy(
                    run_id=run_id,
                    request_id=request_id,
                    strategies=[strategy],
                )
            except Exception as exc:
                attempts.append(f"{strategy.name}:search_error={type(exc).__name__}")
                continue

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
                candidate_id = str(
                    candidate.item.get("id")
                    or candidate.item.get("asset_id")
                    or "unknown"
                )
                if quality_result.decision.value == "reject":
                    attempts.append(
                        f"{strategy.name}:{candidate_id}:quality_reject"
                    )
                    continue
                try:
                    verification = self._semantic_verifier.verify(
                        dict(candidate.item),
                        context=verification_context,
                    )
                except Exception as exc:
                    attempts.append(f"{strategy.name}:verification_error={type(exc).__name__}")
                    continue
                if verification.decision.value in {"uncertain", "reject"}:
                    attempts.append(
                        f"{strategy.name}:{candidate_id}:semantic_"
                        f"{verification.decision.value}"
                    )
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
                    verification_decision=verification.decision.value,
                    semantic_verification_score=verification.score.overall,
                    semantic_verifier=verification.verifier,
                    matched_signals=verification.matched_signals,
                    missing_signals=verification.missing_signals,
                    violated_constraints=verification.violated_constraints,
                    retrieval_attempts=tuple(
                        (*attempts, f"{strategy.name}:{candidate_id}:accepted")
                    ),
                )
            attempts.append(
                f"{strategy.name}:quality_or_verification_rejected={len(eligible)}"
                if eligible
                else f"{strategy.name}:no_semantically_eligible_candidates"
            )
        detail = "; ".join(attempts) or "no strategies executed"
        raise RuntimeError(
            "No stock asset passed semantic relevance, visual quality, and semantic verification gates: "
            + detail
        )
