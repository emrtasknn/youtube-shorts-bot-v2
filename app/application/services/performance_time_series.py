from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.performance_memory import PerformanceTimeSeriesPoint
from app.infrastructure.database.models import PerformanceSnapshotModel, PublicationModel


class PerformanceTimeSeriesNotFoundError(LookupError):
    """Raised when a publication has no usable performance time series."""


class PerformanceTimeSeriesService:
    """Build deterministic growth and time-series features from M7 snapshots."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_publication(self, publication_id: UUID) -> Sequence[PerformanceTimeSeriesPoint]:
        publication = self._session.get(PublicationModel, publication_id)
        if publication is None:
            raise PerformanceTimeSeriesNotFoundError("publication not found")
        if publication.published_at is None:
            raise PerformanceTimeSeriesNotFoundError("publication has no published_at")

        snapshots = self._session.scalars(
            select(PerformanceSnapshotModel)
            .where(PerformanceSnapshotModel.publication_id == publication_id)
            .order_by(PerformanceSnapshotModel.measured_at.asc())
        ).all()
        if not snapshots:
            raise PerformanceTimeSeriesNotFoundError("publication has no performance snapshots")

        points: list[PerformanceTimeSeriesPoint] = []
        previous: PerformanceSnapshotModel | None = None

        for snapshot in snapshots:
            elapsed_hours = Decimal(
                str((snapshot.measured_at - publication.published_at).total_seconds())
            ) / Decimal("3600")

            views_delta: int | None = None
            likes_delta: int | None = None
            comments_delta: int | None = None
            shares_delta: int | None = None
            subscribers_gained_delta: int | None = None
            views_per_hour: Decimal | None = None
            views_growth_rate: Decimal | None = None

            if previous is not None:
                delta_hours = Decimal(
                    str((snapshot.measured_at - previous.measured_at).total_seconds())
                ) / Decimal("3600")
                views_delta = snapshot.views - previous.views
                likes_delta = snapshot.likes - previous.likes
                comments_delta = snapshot.comments - previous.comments
                shares_delta = snapshot.shares - previous.shares
                subscribers_gained_delta = snapshot.subscribers_gained - previous.subscribers_gained

                if delta_hours > 0:
                    views_per_hour = Decimal(views_delta) / delta_hours

                if previous.views > 0:
                    views_growth_rate = Decimal(views_delta) / Decimal(previous.views)

            points.append(
                PerformanceTimeSeriesPoint(
                    publication_id=publication_id,
                    measured_at=snapshot.measured_at,
                    elapsed_hours=elapsed_hours,
                    views=snapshot.views,
                    likes=snapshot.likes,
                    comments=snapshot.comments,
                    shares=snapshot.shares,
                    subscribers_gained=snapshot.subscribers_gained,
                    views_delta=views_delta,
                    likes_delta=likes_delta,
                    comments_delta=comments_delta,
                    shares_delta=shares_delta,
                    subscribers_gained_delta=subscribers_gained_delta,
                    views_per_hour=views_per_hour,
                    views_growth_rate=views_growth_rate,
                    average_view_duration_seconds=snapshot.average_view_duration_seconds,
                    retention=snapshot.retention,
                )
            )
            previous = snapshot

        return tuple(points)
