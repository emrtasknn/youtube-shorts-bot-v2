from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.services.stock_media_scoring import StockMediaScore
from app.application.services.visual_candidate_evidence import CandidateEvidence
from app.application.services.visual_decision import VisualDecision, VisualDecisionEngine
from app.application.services.visual_intent import VisualIntent


@dataclass(frozen=True, slots=True)
class VisualCandidateSelection:
    item: dict[str, Any]
    evidence: CandidateEvidence


class VisualCandidateSelector:
    """Turns scored retrieval candidates into explicit visual decisions."""

    def __init__(self, decision_engine: VisualDecisionEngine | None = None) -> None:
        self._decision_engine = decision_engine or VisualDecisionEngine()

    def evaluate(
        self,
        item: dict[str, Any],
        score: StockMediaScore,
        *,
        intent: VisualIntent,
        source_is_exact: bool,
    ) -> VisualCandidateSelection:
        semantic_relevance = score.relevance
        visual_quality = self._visual_quality(score)
        factual_specificity = self._factual_specificity(
            intent,
            source_is_exact=source_is_exact,
        )
        result = self._decision_engine.decide(
            semantic_relevance=semantic_relevance,
            visual_quality=visual_quality,
            factual_specificity=factual_specificity,
            source_is_exact=source_is_exact,
            must_avoid_match="must_avoid_match" in score.reasons,
            beautifiable=visual_quality >= 0.35,
        )
        evidence = CandidateEvidence.from_score(
            item,
            score,
            intent=intent,
            source_is_exact=source_is_exact,
            decision=result.decision,
            semantic_relevance=semantic_relevance,
            visual_quality=visual_quality,
            factual_specificity=factual_specificity,
            extra_reasons=result.reasons,
        )
        return VisualCandidateSelection(item=item, evidence=evidence)

    def select(
        self,
        candidates: list[tuple[dict[str, Any], StockMediaScore]],
        *,
        intent: VisualIntent,
        source_is_exact: bool,
    ) -> VisualCandidateSelection | None:
        evaluated = [
            self.evaluate(
                item,
                score,
                intent=intent,
                source_is_exact=source_is_exact,
            )
            for item, score in candidates
        ]
        accepted = [
            candidate
            for candidate in evaluated
            if candidate.evidence.decision
            in {
                VisualDecision.ACCEPT_EXACT,
                VisualDecision.ACCEPT_CONTEXTUAL,
                VisualDecision.BEAUTIFY_THEN_ACCEPT,
                VisualDecision.FALLBACK_RELEVANT,
            }
        ]
        if not accepted:
            return None

        decision_rank = {
            VisualDecision.ACCEPT_EXACT: 4,
            VisualDecision.ACCEPT_CONTEXTUAL: 3,
            VisualDecision.BEAUTIFY_THEN_ACCEPT: 2,
            VisualDecision.FALLBACK_RELEVANT: 1,
        }
        return max(
            accepted,
            key=lambda candidate: (
                decision_rank[candidate.evidence.decision],
                candidate.evidence.semantic_relevance,
                candidate.evidence.visual_quality,
                candidate.evidence.factual_specificity,
            ),
        )

    @staticmethod
    def _visual_quality(score: StockMediaScore) -> float:
        return max(
            0.0,
            min(
                1.0,
                score.orientation * 0.35
                + score.resolution * 0.45
                + score.duration * 0.20,
            ),
        )

    @staticmethod
    def _factual_specificity(
        intent: VisualIntent,
        *,
        source_is_exact: bool,
    ) -> float:
        return min(
            1.0,
            intent.specificity + (0.10 if source_is_exact else 0.0),
        )
