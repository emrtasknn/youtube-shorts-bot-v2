from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.application.services.performance_data_quality import PerformanceDataQualityService
from app.domain.performance_memory import (
    PerformanceBaseline,
    PerformanceMemory,
    PerformanceProductionFeatures,
    PerformanceQueryResult,
    PerformanceTimeSeriesPoint,
)


def _result(
    *,
    baseline: PerformanceBaseline | None,
    points: tuple[PerformanceTimeSeriesPoint, ...],
    features: PerformanceProductionFeatures | None = None,
) -> PerformanceQueryResult:
    features = features or PerformanceProductionFeatures(
        category="HISTORY_FACT",
        language="en",
        topic="Roman Empire",
        hook="The Roman Empire did this.",
        scene_count=3,
        visual_providers=("pexels",),
        production_strategy="custom_single_vertical_slice",
    )
    memory = PerformanceMemory(
        publication_id=uuid4(),
        run_id=uuid4(),
        content_id=uuid4(),
        script_id=uuid4(),
        platform="YOUTUBE",
        platform_post_id="video-1",
        published_at=datetime.now(UTC),
        features=features,
    )
    return PerformanceQueryResult(
        memory=memory,
        baseline=baseline,
        time_series=points,
    )


def _point(*, retention: Decimal | None = Decimal("0.5")) -> PerformanceTimeSeriesPoint:
    return PerformanceTimeSeriesPoint(
        publication_id=uuid4(),
        measured_at=datetime.now(UTC),
        elapsed_hours=Decimal("6"),
        views=1000,
        likes=50,
        comments=8,
        shares=4,
        subscribers_gained=5,
        average_view_duration_seconds=Decimal("14"),
        retention=retention,
    )


def _baseline() -> PerformanceBaseline:
    return PerformanceBaseline(
        category="HISTORY_FACT",
        language="en",
        production_strategy="custom_single_vertical_slice",
        sample_count=2,
        average_views=Decimal("1200"),
        average_likes=Decimal("60"),
        average_comments=Decimal("10"),
        average_shares=Decimal("5"),
        average_subscribers_gained=Decimal("6"),
        engagement_rate=Decimal("0.0625"),
        subscriber_conversion_rate=Decimal("0.005"),
    )


def test_data_quality_evaluator_returns_high_confidence_for_complete_memory() -> None:
    result = _result(baseline=_baseline(), points=(_point(), _point()))

    quality = PerformanceDataQualityService().evaluate(result)

    assert quality.confidence == "HIGH"
    assert quality.quality_score == Decimal("1.0")
    assert quality.snapshot_count == 2
    assert quality.production_feature_completeness == Decimal("1")
    assert quality.metric_completeness == Decimal("1")
    assert quality.has_baseline is True
    assert quality.issues == ()


def test_data_quality_evaluator_returns_medium_for_missing_optional_metric() -> None:
    result = _result(
        baseline=_baseline(),
        points=(_point(retention=None), _point()),
    )

    quality = PerformanceDataQualityService().evaluate(result)

    assert quality.confidence == "MEDIUM"
    assert quality.metric_completeness == Decimal("13") / Decimal("14")
    assert "INCOMPLETE_OPTIONAL_METRICS" in quality.issues


def test_data_quality_evaluator_returns_low_without_baseline() -> None:
    result = _result(baseline=None, points=(_point(),))

    quality = PerformanceDataQualityService().evaluate(result)

    assert quality.confidence == "LOW"
    assert quality.has_baseline is False
    assert quality.quality_score == Decimal("0.8")
    assert "NO_BASELINE" in quality.issues


def test_data_quality_evaluator_flags_incomplete_production_features() -> None:
    result = _result(
        baseline=_baseline(),
        points=(_point(), _point()),
        features=PerformanceProductionFeatures(
            category="HISTORY_FACT",
            language="en",
            topic="Roman Empire",
        ),
    )

    quality = PerformanceDataQualityService().evaluate(result)

    assert quality.confidence == "MEDIUM"
    assert quality.production_feature_completeness == Decimal("3") / Decimal("7")
    assert "INCOMPLETE_PRODUCTION_FEATURES" in quality.issues
