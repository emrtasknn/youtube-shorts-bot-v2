from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.application.services.learning_evidence import LearningEvidenceService
from app.domain.learning import ConfidenceLevel, SignalDirection
from app.domain.learning_features import FeatureObservation, LearningFeature
from app.domain.performance_memory import (
    PerformanceBaseline,
    PerformanceDataQuality,
    PerformanceMemory,
    PerformanceProductionFeatures,
    PerformanceQueryResult,
    PerformanceTimeSeriesPoint,
)


def _result(
    *,
    category: str = "history",
    angle: str | None = "mystery",
    duration: Decimal | None = Decimal("35"),
    topic: str = "roman empire",
    views: int = 1200,
    baseline_category: str = "history",
    baseline_views: Decimal = Decimal("1000"),
    quality_score: Decimal = Decimal("1"),
) -> PerformanceQueryResult:
    publication_id = uuid4()
    memory = PerformanceMemory(
        publication_id=publication_id,
        run_id=uuid4(),
        content_id=uuid4(),
        script_id=uuid4(),
        platform="youtube",
        platform_post_id=str(uuid4()),
        published_at=datetime(2026, 10, 1, tzinfo=UTC),
        features=PerformanceProductionFeatures(
            category=category,
            language="en",
            topic=topic,
            angle=angle,
            duration_target_seconds=duration,
        ),
    )
    baseline = PerformanceBaseline(
        category=baseline_category,
        language="en",
        production_strategy=None,
        sample_count=10,
        average_views=baseline_views,
        average_likes=Decimal("10"),
        average_comments=Decimal("2"),
        average_shares=Decimal("1"),
        average_subscribers_gained=Decimal("1"),
        engagement_rate=Decimal("0.01"),
        subscriber_conversion_rate=Decimal("0.001"),
        average_view_duration_seconds=Decimal("25"),
        average_retention=Decimal("0.5"),
    )
    point = PerformanceTimeSeriesPoint(
        publication_id=publication_id,
        measured_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
        elapsed_hours=Decimal("24"),
        views=views,
        likes=10,
        comments=2,
        shares=1,
        subscribers_gained=1,
        average_view_duration_seconds=Decimal("25"),
        retention=Decimal("0.5"),
    )
    quality = PerformanceDataQuality(
        confidence="HIGH",
        quality_score=quality_score,
        snapshot_count=3,
        production_feature_completeness=Decimal("1"),
        metric_completeness=Decimal("1"),
        has_baseline=True,
        time_series_point_count=3,
    )
    return PerformanceQueryResult(
        memory=memory,
        baseline=baseline,
        time_series=(point,),
        quality=quality,
    )


def test_builds_positive_signal_against_single_comparable_baseline() -> None:
    result = _result()
    observation = FeatureObservation(
        feature=LearningFeature.ANGLE,
        feature_value="mystery",
        metric="views",
        observed_value=Decimal("1200"),
        sample_size=3,
    )

    signal = LearningEvidenceService().evaluate(
        (observation,),
        (result,),
        created_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
    )[0]

    assert signal.baseline_value == Decimal("1000")
    assert signal.delta == Decimal("200")
    assert signal.direction is SignalDirection.POSITIVE
    assert signal.confidence is ConfidenceLevel.LOW
    assert signal.evidence.baseline_available is True
    assert signal.evidence.data_quality_score == Decimal("1")


def test_category_does_not_compare_against_its_own_category_baseline() -> None:
    result = _result()
    observation = FeatureObservation(
        feature=LearningFeature.CATEGORY,
        feature_value="history",
        metric="views",
        observed_value=Decimal("1200"),
        sample_size=10,
    )

    signal = LearningEvidenceService().evaluate(
        (observation,),
        (result,),
        created_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
    )[0]

    assert signal.baseline_value is None
    assert signal.delta is None
    assert signal.direction is SignalDirection.NEUTRAL
    assert signal.evidence.baseline_available is False
    assert signal.confidence is ConfidenceLevel.MEDIUM


def test_mixed_baseline_cohorts_are_not_compared() -> None:
    first = _result(baseline_category="history", baseline_views=Decimal("1000"))
    second = _result(baseline_category="science", baseline_views=Decimal("800"))
    observation = FeatureObservation(
        feature=LearningFeature.ANGLE,
        feature_value="mystery",
        metric="views",
        observed_value=Decimal("1100"),
        sample_size=2,
    )

    signal = LearningEvidenceService().evaluate(
        (observation,),
        (first, second),
        created_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
    )[0]

    assert signal.baseline_value is None
    assert signal.evidence.baseline_available is False
    assert signal.confidence is ConfidenceLevel.INSUFFICIENT


def test_zero_quality_forces_insufficient_confidence() -> None:
    result = _result(quality_score=Decimal("0"))
    observation = FeatureObservation(
        feature=LearningFeature.ANGLE,
        feature_value="mystery",
        metric="views",
        observed_value=Decimal("1200"),
        sample_size=10,
    )

    signal = LearningEvidenceService().evaluate(
        (observation,),
        (result,),
        created_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
    )[0]

    assert signal.confidence is ConfidenceLevel.INSUFFICIENT
