from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.application.services.learning_recommendation import LearningRecommendationService
from app.application.services.recommendation_persistence import RecommendationPersistenceService
from app.application.services.recommendation_query import RecommendationQueryService
from app.domain.performance_memory import (
    PerformanceBaseline,
    PerformanceDataQuality,
    PerformanceMemory,
    PerformanceProductionFeatures,
    PerformanceQueryResult,
    PerformanceTimeSeriesPoint,
)


class _ScalarResult:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class _MemorySession:
    def __init__(self) -> None:
        self.model = None

    def scalar(self, _statement: object) -> object:
        return self.model

    def scalars(self, _statement: object) -> _ScalarResult:
        return _ScalarResult([self.model] if self.model is not None else [])

    def add(self, model: object) -> None:
        self.model = model

    def flush(self) -> None:
        pass


def _result(views: int) -> PerformanceQueryResult:
    publication_id = uuid4()
    return PerformanceQueryResult(
        memory=PerformanceMemory(
            publication_id=publication_id,
            run_id=uuid4(),
            content_id=uuid4(),
            script_id=uuid4(),
            platform="youtube",
            platform_post_id=str(uuid4()),
            published_at=datetime(2026, 10, 4, 12, tzinfo=UTC),
            features=PerformanceProductionFeatures(
                category="history",
                language="en",
                topic="topic",
                angle="surprising fact",
                duration_target_seconds=Decimal("30"),
                production_strategy="balanced",
            ),
        ),
        baseline=PerformanceBaseline(
            category="history",
            language="en",
            production_strategy="balanced",
            sample_count=10,
            average_views=Decimal("100"),
            average_likes=Decimal("5"),
            average_comments=Decimal("1"),
            average_shares=Decimal("1"),
            average_subscribers_gained=Decimal("1"),
            engagement_rate=Decimal("0.07"),
            subscriber_conversion_rate=Decimal("0.01"),
        ),
        time_series=(
            PerformanceTimeSeriesPoint(
                publication_id=publication_id,
                measured_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
                elapsed_hours=Decimal("24"),
                views=views,
                likes=5,
                comments=1,
                shares=1,
                subscribers_gained=1,
            ),
        ),
        quality=PerformanceDataQuality(
            confidence="HIGH",
            quality_score=Decimal("1"),
            snapshot_count=1,
            production_feature_completeness=Decimal("1"),
            metric_completeness=Decimal("1"),
            has_baseline=True,
            time_series_point_count=1,
        ),
    )


def test_m9_generate_persist_query_regression() -> None:
    results = (_result(120), _result(130), _result(110))
    recommendations = LearningRecommendationService().generate(
        results,
        created_at=datetime(2026, 10, 5, 15, tzinfo=UTC),
    )

    session = _MemorySession()
    persistence = RecommendationPersistenceService(session)
    saved = persistence.save(recommendations[0])

    queried = RecommendationQueryService(session).get(saved.recommendation_id)

    assert queried == saved
    assert queried is not None
    assert queried.signal.baseline_value is not None
    assert queried.text
