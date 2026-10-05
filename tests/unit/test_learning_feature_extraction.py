from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.application.services.learning_feature_extraction import LearningFeatureExtractionService
from app.domain.learning_features import LearningFeature, duration_bucket
from app.domain.performance_memory import (
    PerformanceMemory,
    PerformanceProductionFeatures,
    PerformanceQueryResult,
    PerformanceTimeSeriesPoint,
)


def make_result(
    *,
    category: str = "HISTORY_FACT",
    angle: str | None = "final_breach",
    topic: str = "The fall of Constantinople",
    duration: str = "34",
    views: int = 1000,
    retention: str = "0.50",
) -> PerformanceQueryResult:
    publication_id = uuid4()
    return PerformanceQueryResult(
        memory=PerformanceMemory(
            publication_id=publication_id,
            run_id=uuid4(),
            content_id=uuid4(),
            script_id=uuid4(),
            platform="YOUTUBE",
            platform_post_id=f"video-{publication_id}",
            published_at=datetime(2026, 10, 4, tzinfo=UTC),
            features=PerformanceProductionFeatures(
                category=category,
                language="en",
                topic=topic,
                angle=angle,
                duration_target_seconds=Decimal(duration),
            ),
        ),
        baseline=None,
        time_series=(
            PerformanceTimeSeriesPoint(
                publication_id=publication_id,
                measured_at=datetime(2026, 10, 5, tzinfo=UTC),
                elapsed_hours=Decimal("24"),
                views=views,
                likes=10,
                comments=2,
                shares=1,
                subscribers_gained=1,
                average_view_duration_seconds=Decimal("17.5"),
                retention=Decimal(retention),
            ),
        ),
    )


def test_duration_bucket_is_deterministic() -> None:
    assert duration_bucket(Decimal("19")) == "<20s"
    assert duration_bucket(Decimal("20")) == "20-29s"
    assert duration_bucket(Decimal("30")) == "30-39s"
    assert duration_bucket(Decimal("40")) == "40-49s"
    assert duration_bucket(Decimal("50")) == "50s+"


def test_extractor_groups_feature_cohorts_and_averages_metrics() -> None:
    service = LearningFeatureExtractionService()

    observations = service.extract(
        [
            make_result(views=1000, retention="0.40"),
            make_result(views=3000, retention="0.60"),
        ]
    )

    category_retention = next(
        item
        for item in observations
        if item.feature is LearningFeature.CATEGORY and item.metric == "retention"
    )
    category_views = next(
        item
        for item in observations
        if item.feature is LearningFeature.CATEGORY and item.metric == "views"
    )

    assert category_retention.feature_value == "HISTORY_FACT"
    assert category_retention.sample_size == 2
    assert category_retention.observed_value == Decimal("0.50")

    assert category_views.sample_size == 2
    assert category_views.observed_value == Decimal("2000")


def test_extractor_skips_missing_optional_features_and_metrics() -> None:
    service = LearningFeatureExtractionService()

    observations = service.extract(
        [
            make_result(angle=None, duration="34", retention="0.50"),
        ]
    )

    assert not any(item.feature is LearningFeature.ANGLE for item in observations)
    assert any(
        item.feature is LearningFeature.DURATION_BUCKET and item.feature_value == "30-39s"
        for item in observations
    )


def test_extractor_does_not_treat_raw_hook_text_as_a_hook_type() -> None:
    result = make_result()
    observations = LearningFeatureExtractionService().extract([result])

    assert not any(item.feature.value == "hook_type" for item in observations)
