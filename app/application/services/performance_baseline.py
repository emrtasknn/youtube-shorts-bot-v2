from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.services.performance_aggregation import PerformanceAggregationService
from app.domain.performance_memory import PerformanceAggregate, PerformanceBaseline


class PerformanceBaselineService:
    """Build deterministic baselines from persisted performance cohorts."""

    def __init__(self, session: Session) -> None:
        self._aggregation = PerformanceAggregationService(session)

    def build_baseline(
        self,
        *,
        category: str | None = None,
        language: str | None = None,
        platform: str | None = None,
    ) -> Sequence[PerformanceBaseline]:
        aggregates = self._aggregation.aggregate_by_production_strategy(
            category=category,
            language=language,
            platform=platform,
        )
        return tuple(self._to_baseline(aggregate) for aggregate in aggregates)

    @staticmethod
    def _to_baseline(aggregate: PerformanceAggregate) -> PerformanceBaseline:
        sample_count = Decimal(aggregate.sample_count)
        average_views = Decimal(aggregate.views_total) / sample_count
        average_likes = Decimal(aggregate.likes_total) / sample_count
        average_comments = Decimal(aggregate.comments_total) / sample_count
        average_shares = Decimal(aggregate.shares_total) / sample_count
        average_subscribers = Decimal(aggregate.subscribers_gained_total) / sample_count

        if aggregate.views_total:
            engagement_rate = Decimal(
                aggregate.likes_total + aggregate.comments_total + aggregate.shares_total
            ) / Decimal(aggregate.views_total)
            subscriber_conversion_rate = Decimal(aggregate.subscribers_gained_total) / Decimal(
                aggregate.views_total
            )
        else:
            engagement_rate = Decimal("0")
            subscriber_conversion_rate = Decimal("0")

        return PerformanceBaseline(
            category=aggregate.category,
            language=aggregate.language,
            production_strategy=aggregate.production_strategy,
            sample_count=aggregate.sample_count,
            average_views=average_views,
            average_likes=average_likes,
            average_comments=average_comments,
            average_shares=average_shares,
            average_subscribers_gained=average_subscribers,
            engagement_rate=engagement_rate,
            subscriber_conversion_rate=subscriber_conversion_rate,
            average_view_duration_seconds=aggregate.average_view_duration_seconds,
            average_retention=aggregate.average_retention,
        )
