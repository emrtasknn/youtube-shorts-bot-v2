from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.application.services.learning_recommendation import LearningRecommendationService
from app.domain.learning import RecommendationStatus, SignalDirection
from app.domain.performance_memory import (
    PerformanceBaseline,
    PerformanceDataQuality,
    PerformanceMemory,
    PerformanceProductionFeatures,
    PerformanceQueryResult,
    PerformanceTimeSeriesPoint,
)


def _result(index: int, views: int) -> PerformanceQueryResult:
    publication_id = uuid4()
    measured_at = datetime(2026, 10, 5, 12 + index, tzinfo=UTC)
    return PerformanceQueryResult(
        memory=PerformanceMemory(
            publication_id=publication_id,
            run_id=uuid4(),
            content_id=uuid4(),
            script_id=uuid4(),
            platform="youtube",
            platform_post_id=f"video-{index}",
            published_at=datetime(2026, 10, 4, 12, tzinfo=UTC),
            features=PerformanceProductionFeatures(
                category="history",
                language="en",
                topic=f"topic-{index}",
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
            average_view_duration_seconds=Decimal("20"),
            average_retention=Decimal("0.67"),
        ),
        time_series=(
            PerformanceTimeSeriesPoint(
                publication_id=publication_id,
                measured_at=measured_at,
                elapsed_hours=Decimal("24"),
                views=views,
                likes=5,
                comments=1,
                shares=1,
                subscribers_gained=1,
                average_view_duration_seconds=Decimal("20"),
                retention=Decimal("0.67"),
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


def test_learning_recommendation_service_composes_deterministic_pipeline() -> None:
    results = (_result(0, 120), _result(1, 130), _result(2, 110))

    recommendations = LearningRecommendationService().generate(
        results,
        created_at=datetime(2026, 10, 5, 15, tzinfo=UTC),
    )

    matching = [
        recommendation
        for recommendation in recommendations
        if recommendation.signal.feature == "angle" and recommendation.signal.metric == "views"
    ]
    assert len(matching) == 1
    recommendation = matching[0]
    assert recommendation.signal.observed_value == Decimal("120")
    assert recommendation.signal.baseline_value == Decimal("100")
    assert recommendation.signal.delta == Decimal("20")
    assert recommendation.signal.direction is SignalDirection.POSITIVE
    assert recommendation.status is RecommendationStatus.GENERATED


def test_learning_recommendation_service_materializes_results_once() -> None:
    results = iter((_result(0, 120), _result(1, 130), _result(2, 110)))

    recommendations = LearningRecommendationService().generate(
        results,
        created_at=datetime(2026, 10, 5, 15, tzinfo=UTC),
    )

    assert recommendations
