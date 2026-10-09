from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.application.ports.stock_media import StockMediaGateway, StockMediaStrategy
from app.application.services.real_vision_verifier import (
    CostAwareVisionVerifier,
    GeminiVisionSemanticVerifier,
    VisionVerificationConfig,
)
from app.application.services.scene_contract import SceneContract
from app.application.services.stock_media_quality import StockMediaQualityEvaluator
from app.application.services.stock_media_scoring import StockMediaScorer
from app.application.services.stock_media_selector import StockMediaSelector
from app.application.services.visual_beat import VisualBeat
from app.application.services.visual_beat_retrieval import to_visual_relevance_context
from app.application.services.visual_candidate_pool import VisualCandidatePool
from app.application.services.visual_query_expansion import VisualQueryExpander
from app.application.services.visual_semantic_verifier import (
    DeterministicVisualSemanticVerifier,
    VisualSemanticVerifier,
    VisualVerificationContext,
    to_visual_verification_context,
)
from app.application.services.visual_source_resolver import VisualSourceResolver
from app.application.services.visual_variety import VisualVarietyEngine
from app.application.use_cases.search_stock_media import SearchStockMedia
from app.config.settings import get_settings


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
    query_name: str = "primary"
    query_trace: tuple[str, ...] = ()
    candidate_pool_size: int = 0
    candidate_queries: tuple[str, ...] = ()
    candidate_providers: tuple[str, ...] = ()
    variety_score: float = 1.0
    variety_penalties: tuple[str, ...] = ()
    variety_signals: tuple[str, ...] = ()


def _looks_historical(era: str) -> bool:
    return bool(
        re.search(
            r"\b(?:\d{3,4}|ancient|medieval|roman|soviet|century|bc|ad)\b",
            era.lower(),
        )
    )


class VisualBeatRetriever:
    """M24 multi-query retrieval over a bounded canonical candidate pool."""

    def __init__(
        self,
        gateway: StockMediaGateway,
        *,
        semantic_verifier: VisualSemanticVerifier | None = None,
        max_queries: int = 5,
        max_candidates: int = 40,
        candidates_per_query: int = 10,
    ) -> None:
        self._search = SearchStockMedia(gateway)
        self._selector = StockMediaSelector(StockMediaScorer())
        self._quality_evaluator = StockMediaQualityEvaluator()
        if semantic_verifier is not None:
            self._semantic_verifier = semantic_verifier
        else:
            settings = get_settings()
            if settings.gemini_enabled and settings.gemini_api_key:
                self._semantic_verifier = CostAwareVisionVerifier(
                    GeminiVisionSemanticVerifier(
                        VisionVerificationConfig(
                            api_key=settings.gemini_api_key,
                            model=settings.gemini_model,
                            base_url=settings.gemini_base_url,
                            timeout_seconds=settings.gemini_timeout_seconds,
                        )
                    ),
                    max_verified_candidates=6,
                )
            else:
                self._semantic_verifier = DeterministicVisualSemanticVerifier()
        self._query_expander = VisualQueryExpander()
        self._max_queries = max_queries
        self._max_candidates = max_candidates
        self._candidates_per_query = candidates_per_query
        self._variety = VisualVarietyEngine()

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

        query_plan = self._query_expander.expand(scene)
        variants = query_plan.bounded_variants[: self._max_queries]
        historical = _looks_historical(beat.era)
        provider_candidates = ("wikimedia_commons",) if historical else None
        strategies = [
            StockMediaStrategy(
                name=variant.name,
                query=variant.query,
                operation="search_photos",
                orientation=None if historical else "portrait",
                provider_candidates=provider_candidates,
                min_relevance=variant.min_relevance,
            )
            for variant in variants
        ]
        relevance_context = to_visual_relevance_context(beat)
        verification_context: VisualVerificationContext = to_visual_verification_context(beat)
        pool = VisualCandidatePool(max_candidates=self._max_candidates)
        attempts: list[str] = []
        query_trace: list[str] = []

        for strategy, variant in zip(strategies, variants, strict=True):
            try:
                result = await self._search.execute_strategy(
                    run_id=run_id,
                    request_id=f"{request_id}:{variant.name}",
                    strategies=[strategy],
                    metadata={
                        "m24_query_name": variant.name,
                        "m24_query_priority": variant.priority,
                    },
                )
            except Exception as exc:
                attempts.append(f"{variant.name}:search_error={type(exc).__name__}")
                query_trace.append(f"{variant.name}:error:{type(exc).__name__}")
                continue

            query_trace.append(
                f"{variant.name}:provider={result.provider}:results={len(result.items)}"
            )
            ranked = self._selector.rank(
                result.items,
                query=variant.query,
                min_relevance=variant.min_relevance,
                relevance_context=relevance_context,
            )
            eligible = [
                candidate
                for candidate in ranked
                if candidate.score.eligible and candidate.score.relevance >= variant.min_relevance
            ][: self._candidates_per_query]
            pool.add(eligible, query=variant, provider=result.provider)
            attempts.append(f"{variant.name}:provider={result.provider}:candidates={len(eligible)}")

        ranked_pool = pool.ranked()
        variety_ranked_pool = self._variety.rank(
            ranked_pool,
            run_id=run_id,
            subject_terms=beat.entities,
        )
        vision_shortlist = variety_ranked_pool[:6]
        for entry in vision_shortlist:
            quality_result = self._quality_evaluator.evaluate(entry.score)
            candidate_id = entry.asset_id or "unknown"
            variety = self._variety.evaluate(
                self._variety.profile(entry, subject_terms=beat.entities),
                history=self._variety.history(run_id),
            )
            if quality_result.decision.value == "reject":
                attempts.append(f"pool:{candidate_id}:quality_reject")
                continue

            try:
                verification = self._semantic_verifier.verify(
                    dict(entry.item),
                    context=verification_context,
                )
            except Exception as exc:
                attempts.append(f"pool:{candidate_id}:verification_error={type(exc).__name__}")
                continue

            if verification.decision.value in {"uncertain", "reject"}:
                attempts.append(f"pool:{candidate_id}:semantic_{verification.decision.value}")
                continue

            self._variety.remember(
                run_id=run_id,
                item=dict(entry.item),
                provider=entry.providers[0] if entry.providers else "unknown",
                subject_terms=beat.entities,
            )
            selected_query = entry.queries[0] if entry.queries else ""
            selected_query_name = entry.query_names[0] if entry.query_names else "unknown"
            return VisualBeatRetrievalResult(
                beat=beat,
                provider=entry.providers[0] if entry.providers else "unknown",
                query=selected_query,
                item=dict(entry.item),
                score=entry.score.score,
                quality_decision=quality_result.decision.value,
                visual_quality=quality_result.score.overall,
                beautifiable=quality_result.score.beautifiable,
                verification_decision=verification.decision.value,
                semantic_verification_score=verification.score.overall,
                semantic_verifier=verification.verifier,
                matched_signals=verification.matched_signals,
                missing_signals=verification.missing_signals,
                violated_constraints=verification.violated_constraints,
                retrieval_attempts=tuple((*attempts, f"pool:{candidate_id}:accepted")),
                query_name=selected_query_name,
                query_trace=tuple(query_trace),
                candidate_pool_size=len(pool),
                candidate_queries=entry.queries,
                candidate_providers=entry.providers,
                variety_score=variety.score,
                variety_penalties=variety.penalties,
                variety_signals=variety.signals,
            )

        detail = "; ".join(attempts) or "no strategies executed"
        raise RuntimeError(
            "No stock asset passed semantic relevance, visual quality, and semantic verification gates: "
            + detail
        )
