from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.recommendation_persistence import (
    RecommendationPersistenceService,
)
from app.domain.learning import (
    ConfidenceLevel,
    Recommendation,
    RecommendationStatus,
    SignalDirection,
)
from app.infrastructure.database.models import RecommendationModel


class RecommendationQueryService:
    """Read persisted recommendations using deterministic filters and ordering."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, recommendation_id: UUID) -> Recommendation | None:
        model = self._session.scalar(
            select(RecommendationModel).where(
                RecommendationModel.recommendation_id == recommendation_id
            )
        )
        if model is None:
            return None
        return RecommendationPersistenceService.to_recommendation(model)

    def list(
        self,
        *,
        status: RecommendationStatus | None = None,
        feature: str | None = None,
        metric: str | None = None,
        confidence: ConfidenceLevel | None = None,
        direction: SignalDirection | None = None,
        limit: int = 100,
    ) -> tuple[Recommendation, ...]:
        if limit <= 0:
            raise ValueError("Recommendation query limit must be positive")

        statement = select(RecommendationModel)
        if status is not None:
            statement = statement.where(RecommendationModel.status == status.value)
        if feature is not None:
            statement = statement.where(RecommendationModel.feature == feature)
        if metric is not None:
            statement = statement.where(RecommendationModel.metric == metric)
        if confidence is not None:
            statement = statement.where(RecommendationModel.confidence == confidence.value)
        if direction is not None:
            statement = statement.where(RecommendationModel.direction == direction.value)

        statement = (
            statement.order_by(
                RecommendationModel.created_at.desc(),
                RecommendationModel.recommendation_id.desc(),
            )
            .limit(limit)
        )
        models = self._session.scalars(statement).all()
        return tuple(RecommendationPersistenceService.to_recommendation(model) for model in models)
