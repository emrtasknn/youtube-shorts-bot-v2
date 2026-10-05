from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.learning import (
    ConfidenceLevel,
    LearningEvidence,
    LearningSignal,
    Recommendation,
    RecommendationStatus,
    SignalDirection,
)
from app.infrastructure.database.models import RecommendationModel


class RecommendationPersistenceService:
    """Persist generated learning recommendations idempotently."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, recommendation: Recommendation) -> Recommendation:
        existing = self._session.scalar(
            select(RecommendationModel).where(
                RecommendationModel.recommendation_id == recommendation.recommendation_id
            )
        )
        if existing is not None:
            return self._to_recommendation(existing)

        signal = recommendation.signal
        model = RecommendationModel(
            recommendation_id=recommendation.recommendation_id,
            signal_id=signal.signal_id,
            feature=signal.feature,
            feature_value=signal.feature_value,
            metric=signal.metric,
            observed_value=signal.observed_value,
            baseline_value=signal.baseline_value,
            delta=signal.delta,
            sample_size=signal.evidence.sample_size,
            baseline_available=signal.evidence.baseline_available,
            data_quality_score=signal.evidence.data_quality_score,
            notes=list(signal.evidence.notes),
            confidence=signal.confidence.value,
            direction=signal.direction.value,
            text=recommendation.text,
            status=recommendation.status.value,
            created_at=recommendation.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return recommendation

    def save_many(
        self,
        recommendations: tuple[Recommendation, ...],
    ) -> tuple[Recommendation, ...]:
        return tuple(self.save(recommendation) for recommendation in recommendations)

    @staticmethod
    def _to_recommendation(model: RecommendationModel) -> Recommendation:
        evidence = LearningEvidence(
            sample_size=model.sample_size,
            baseline_available=model.baseline_available,
            data_quality_score=Decimal(str(model.data_quality_score)),
            notes=tuple(note for note in model.notes if isinstance(note, str)),
        )
        signal = LearningSignal(
            signal_id=model.signal_id,
            feature=model.feature,
            feature_value=model.feature_value,
            metric=model.metric,
            observed_value=Decimal(str(model.observed_value)),
            baseline_value=(
                Decimal(str(model.baseline_value)) if model.baseline_value is not None else None
            ),
            delta=Decimal(str(model.delta)) if model.delta is not None else None,
            evidence=evidence,
            confidence=ConfidenceLevel(model.confidence),
            direction=SignalDirection(model.direction),
            created_at=model.created_at,
        )
        return Recommendation(
            recommendation_id=model.recommendation_id,
            signal=signal,
            text=model.text,
            status=RecommendationStatus(model.status),
            created_at=model.created_at,
        )

    @staticmethod
    def parse_recommendation_id(recommendation_id: str) -> UUID:
        try:
            return UUID(recommendation_id)
        except ValueError as exc:
            raise ValueError("recommendation_id must be a valid UUID") from exc
