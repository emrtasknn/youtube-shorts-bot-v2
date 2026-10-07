from __future__ import annotations

from app.application.services.stock_media_scoring import StockMediaScore
from app.application.services.visual_quality import (
    VisualQualityDecisionResult,
    VisualQualityEvaluator,
)


class StockMediaQualityEvaluator:
    """Maps existing M17 measurable signals into the M19 quality contract."""

    def __init__(self, evaluator: VisualQualityEvaluator | None = None) -> None:
        self._evaluator = evaluator or VisualQualityEvaluator()

    def evaluate(self, score: StockMediaScore) -> VisualQualityDecisionResult:
        overall = max(
            0.0,
            min(
                1.0,
                score.orientation * 0.35 + score.resolution * 0.45 + score.duration * 0.20,
            ),
        )
        return self._evaluator.evaluate(
            composition=score.orientation,
            resolution=score.resolution,
            portrait_fit=score.orientation,
            cleanliness=score.duration,
            beautifiable=overall < 0.75,
        )
