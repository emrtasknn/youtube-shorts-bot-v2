from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.performance_memory import PerformanceAggregate
from app.infrastructure.database.models import (
    PerformanceProductionSnapshotModel,
    PerformanceSnapshotModel,
)


class PerformanceAggregationService:
    """Build deterministic performance cohorts from persisted M7/M8 snapshots."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def aggregate_by_production_strategy(
        self,
        *,
        category: str | None = None,
        language: str | None = None,
        platform: str | None = None,
    ) -> Sequence[PerformanceAggregate]:
        stmt = (
            select(
                PerformanceProductionSnapshotModel.category,
                PerformanceProductionSnapshotModel.language,
                PerformanceProductionSnapshotModel.production_strategy,
                func.count(PerformanceSnapshotModel.id),
                func.coalesce(func.sum(PerformanceSnapshotModel.views), 0),
                func.coalesce(func.sum(PerformanceSnapshotModel.likes), 0),
                func.coalesce(func.sum(PerformanceSnapshotModel.comments), 0),
                func.coalesce(func.sum(PerformanceSnapshotModel.shares), 0),
                func.coalesce(func.sum(PerformanceSnapshotModel.subscribers_gained), 0),
                func.avg(PerformanceSnapshotModel.average_view_duration_seconds),
                func.avg(PerformanceSnapshotModel.retention),
            )
            .join(
                PerformanceSnapshotModel,
                PerformanceSnapshotModel.publication_id
                == PerformanceProductionSnapshotModel.publication_id,
            )
            .where(PerformanceSnapshotModel.platform == PerformanceProductionSnapshotModel.platform)
            .group_by(
                PerformanceProductionSnapshotModel.category,
                PerformanceProductionSnapshotModel.language,
                PerformanceProductionSnapshotModel.production_strategy,
            )
            .order_by(
                PerformanceProductionSnapshotModel.category,
                PerformanceProductionSnapshotModel.language,
                PerformanceProductionSnapshotModel.production_strategy,
            )
        )
        if category is not None:
            stmt = stmt.where(PerformanceProductionSnapshotModel.category == category)
        if language is not None:
            stmt = stmt.where(PerformanceProductionSnapshotModel.language == language)
        if platform is not None:
            stmt = stmt.where(PerformanceSnapshotModel.platform == platform)

        rows = self._session.execute(stmt).all()
        return tuple(self._to_aggregate(row) for row in rows)

    @staticmethod
    def _to_aggregate(row: tuple[object, ...]) -> PerformanceAggregate:
        (
            category,
            language,
            production_strategy,
            sample_count,
            views_total,
            likes_total,
            comments_total,
            shares_total,
            subscribers_gained_total,
            average_view_duration_seconds,
            average_retention,
        ) = row
        return PerformanceAggregate(
            category=str(category),
            language=str(language),
            production_strategy=(
                str(production_strategy) if production_strategy is not None else None
            ),
            sample_count=cast(int, sample_count),
            views_total=cast(int, views_total),
            likes_total=cast(int, likes_total),
            comments_total=cast(int, comments_total),
            shares_total=cast(int, shares_total),
            subscribers_gained_total=cast(int, subscribers_gained_total),
            average_view_duration_seconds=(
                Decimal(str(average_view_duration_seconds))
                if average_view_duration_seconds is not None
                else None
            ),
            average_retention=(
                Decimal(str(average_retention)) if average_retention is not None else None
            ),
        )
