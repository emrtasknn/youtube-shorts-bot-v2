from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.application.services.stock_media_quality import StockMediaQualityEvaluator
from app.application.services.stock_media_selector import ScoredStockMedia


@dataclass(frozen=True, slots=True)
class QualityGateSelection:
    candidate: ScoredStockMedia
    decision: str
    visual_quality: float
    beautifiable: bool


class M19QualityGate:
    """Apply the M19 quality gate to M17-ranked candidates."""

    def __init__(self, evaluator: StockMediaQualityEvaluator | None = None) -> None:
        self._evaluator = evaluator or StockMediaQualityEvaluator()

    def select(
        self, candidates: Iterable[ScoredStockMedia]
    ) -> QualityGateSelection | None:
        for candidate in candidates:
            result = self._evaluator.evaluate(candidate.score)
            if result.decision.value == "reject":
                continue
            return QualityGateSelection(
                candidate=candidate,
                decision=result.decision.value,
                visual_quality=result.score.overall,
                beautifiable=result.score.beautifiable,
            )
        return None
