from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from app.application.services.learning_evidence import LearningEvidenceService
from app.application.services.learning_feature_extraction import LearningFeatureExtractionService
from app.application.services.recommendation_engine import RecommendationEngine
from app.domain.learning import Recommendation
from app.domain.performance_memory import PerformanceQueryResult


class LearningRecommendationService:
    """Integrate deterministic learning stages without mutating production decisions."""

    def __init__(
        self,
        feature_extraction: LearningFeatureExtractionService | None = None,
        evidence: LearningEvidenceService | None = None,
        recommendations: RecommendationEngine | None = None,
    ) -> None:
        self._feature_extraction = feature_extraction or LearningFeatureExtractionService()
        self._evidence = evidence or LearningEvidenceService()
        self._recommendations = recommendations or RecommendationEngine()

    def generate(
        self,
        results: Iterable[PerformanceQueryResult],
        *,
        created_at: datetime,
    ) -> tuple[Recommendation, ...]:
        materialized_results = tuple(results)
        observations = self._feature_extraction.extract(materialized_results)
        signals = self._evidence.evaluate(
            observations,
            materialized_results,
            created_at=created_at,
        )
        return self._recommendations.generate(signals)
