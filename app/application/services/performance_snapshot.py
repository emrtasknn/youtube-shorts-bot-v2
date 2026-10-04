from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.analytics import VideoPerformance
from app.infrastructure.database.models import PerformanceSnapshotModel


class PerformanceSnapshotService:
    """Persists immutable analytics snapshots for published videos."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, performance: VideoPerformance) -> VideoPerformance:
        publication_id = self._parse_publication_id(performance.publication_id)
        existing = self._session.scalar(
            select(PerformanceSnapshotModel).where(
                PerformanceSnapshotModel.publication_id == publication_id,
                PerformanceSnapshotModel.measured_at == performance.measured_at,
            )
        )
        if existing is not None:
            return self._to_performance(existing)

        model = PerformanceSnapshotModel(
            publication_id=publication_id,
            platform=performance.platform,
            platform_post_id=performance.platform_post_id,
            measured_at=performance.measured_at,
            views=performance.views,
            likes=performance.likes,
            comments=performance.comments,
            shares=performance.shares,
            subscribers_gained=performance.subscribers_gained,
            watch_time_seconds=(
                Decimal(str(performance.watch_time_seconds))
                if performance.watch_time_seconds is not None
                else None
            ),
            average_view_duration_seconds=(
                Decimal(str(performance.average_view_duration_seconds))
                if performance.average_view_duration_seconds is not None
                else None
            ),
            retention=(
                Decimal(str(performance.retention)) if performance.retention is not None else None
            ),
        )
        self._session.add(model)
        self._session.flush()
        return performance

    def list_for_publication(
        self,
        publication_id: str,
        *,
        limit: int = 100,
    ) -> tuple[VideoPerformance, ...]:
        parsed_id = self._parse_publication_id(publication_id)
        if limit <= 0:
            raise ValueError("Performance snapshot limit must be positive")

        models = self._session.scalars(
            select(PerformanceSnapshotModel)
            .where(PerformanceSnapshotModel.publication_id == parsed_id)
            .order_by(PerformanceSnapshotModel.measured_at.desc())
            .limit(limit)
        ).all()
        return tuple(self._to_performance(model) for model in models)

    @staticmethod
    def _parse_publication_id(publication_id: str) -> UUID:
        try:
            return UUID(publication_id)
        except ValueError as exc:
            raise ValueError("publication_id must be a valid UUID") from exc

    @staticmethod
    def _to_performance(model: PerformanceSnapshotModel) -> VideoPerformance:
        return VideoPerformance(
            publication_id=str(model.publication_id),
            platform=model.platform,
            platform_post_id=model.platform_post_id,
            measured_at=model.measured_at,
            views=model.views,
            likes=model.likes,
            comments=model.comments,
            shares=model.shares,
            subscribers_gained=model.subscribers_gained,
            watch_time_seconds=(
                float(model.watch_time_seconds) if model.watch_time_seconds is not None else None
            ),
            average_view_duration_seconds=(
                float(model.average_view_duration_seconds)
                if model.average_view_duration_seconds is not None
                else None
            ),
            retention=float(model.retention) if model.retention is not None else None,
        )
