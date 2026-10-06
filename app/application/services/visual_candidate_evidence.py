from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.services.stock_media_scoring import StockMediaScore
from app.application.services.visual_decision import VisualDecision
from app.application.services.visual_intent import VisualIntent


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    """Explain why a retrieved asset is safe and useful for a visual intent."""

    provider_asset_id: str
    decision: VisualDecision
    semantic_relevance: float
    visual_quality: float
    factual_specificity: float
    matched_terms: tuple[str, ...]
    reasons: tuple[str, ...]
    source_is_exact: bool
    source_priority: str

    @classmethod
    def from_score(
        cls,
        item: dict[str, Any],
        score: StockMediaScore,
        *,
        intent: VisualIntent,
        source_is_exact: bool,
        decision: VisualDecision,
        semantic_relevance: float,
        visual_quality: float,
        factual_specificity: float,
        extra_reasons: tuple[str, ...] = (),
    ) -> CandidateEvidence:
        provider_asset_id = str(item.get("id", ""))
        reasons = tuple(dict.fromkeys((*score.reasons, *extra_reasons)))
        return cls(
            provider_asset_id=provider_asset_id,
            decision=decision,
            semantic_relevance=semantic_relevance,
            visual_quality=visual_quality,
            factual_specificity=factual_specificity,
            matched_terms=score.matched_terms,
            reasons=reasons,
            source_is_exact=source_is_exact,
            source_priority=intent.source_priority.value,
        )

    def __post_init__(self) -> None:
        for name, value in (
            ("semantic_relevance", self.semantic_relevance),
            ("visual_quality", self.visual_quality),
            ("factual_specificity", self.factual_specificity),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
