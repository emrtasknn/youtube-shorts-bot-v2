from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class VisualDecision(StrEnum):
    ACCEPT_EXACT = "accept_exact"
    ACCEPT_CONTEXTUAL = "accept_contextual"
    BEAUTIFY_THEN_ACCEPT = "beautify_then_accept"
    FALLBACK_RELEVANT = "fallback_relevant"
    REJECT_NO_SAFE_VISUAL = "reject_no_safe_visual"


@dataclass(frozen=True, slots=True)
class VisualDecisionResult:
    decision: VisualDecision
    semantic_relevance: float
    visual_quality: float
    factual_specificity: float
    reasons: tuple[str, ...]
    enhancement_required: bool = False

    def __post_init__(self) -> None:
        for name, value in (
            ("semantic_relevance", self.semantic_relevance),
            ("visual_quality", self.visual_quality),
            ("factual_specificity", self.factual_specificity),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


class VisualDecisionEngine:
    """Keeps semantic truth ahead of aesthetics in visual selection."""

    def decide(
        self,
        *,
        semantic_relevance: float,
        visual_quality: float,
        factual_specificity: float,
        source_is_exact: bool,
        must_avoid_match: bool = False,
        beautifiable: bool = True,
    ) -> VisualDecisionResult:
        if must_avoid_match:
            return self._result(
                VisualDecision.REJECT_NO_SAFE_VISUAL,
                semantic_relevance,
                visual_quality,
                factual_specificity,
                "must_avoid_match",
            )

        if semantic_relevance < 0.40:
            return self._result(
                VisualDecision.REJECT_NO_SAFE_VISUAL,
                semantic_relevance,
                visual_quality,
                factual_specificity,
                "semantic_relevance_below_safe_floor",
            )

        if source_is_exact and semantic_relevance >= 0.80:
            if visual_quality >= 0.65:
                decision = VisualDecision.ACCEPT_EXACT
            elif beautifiable:
                decision = VisualDecision.BEAUTIFY_THEN_ACCEPT
            else:
                decision = VisualDecision.FALLBACK_RELEVANT
            return self._result(
                decision,
                semantic_relevance,
                visual_quality,
                factual_specificity,
                "exact_source_preferred",
                enhancement_required=decision == VisualDecision.BEAUTIFY_THEN_ACCEPT,
            )

        if semantic_relevance >= 0.65 and visual_quality >= 0.65:
            return self._result(
                VisualDecision.ACCEPT_CONTEXTUAL,
                semantic_relevance,
                visual_quality,
                factual_specificity,
                "strong_contextual_match",
            )

        if semantic_relevance >= 0.65:
            if beautifiable:
                return self._result(
                    VisualDecision.BEAUTIFY_THEN_ACCEPT,
                    semantic_relevance,
                    visual_quality,
                    factual_specificity,
                    "relevant_but_needs_enhancement",
                    enhancement_required=True,
                )
            return self._result(
                VisualDecision.FALLBACK_RELEVANT,
                semantic_relevance,
                visual_quality,
                factual_specificity,
                "relevant_but_not_beautifiable",
            )

        if visual_quality >= 0.90:
            return self._result(
                VisualDecision.REJECT_NO_SAFE_VISUAL,
                semantic_relevance,
                visual_quality,
                factual_specificity,
                "beautiful_but_semantically_weak",
            )

        return self._result(
            VisualDecision.REJECT_NO_SAFE_VISUAL,
            semantic_relevance,
            visual_quality,
            factual_specificity,
            "insufficient_semantic_relevance",
        )

    @staticmethod
    def _result(
        decision: VisualDecision,
        semantic_relevance: float,
        visual_quality: float,
        factual_specificity: float,
        reason: str,
        *,
        enhancement_required: bool = False,
    ) -> VisualDecisionResult:
        return VisualDecisionResult(
            decision=decision,
            semantic_relevance=semantic_relevance,
            visual_quality=visual_quality,
            factual_specificity=factual_specificity,
            reasons=(reason,),
            enhancement_required=enhancement_required,
        )
