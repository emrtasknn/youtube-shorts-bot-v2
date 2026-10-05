from decimal import Decimal

import pytest

from app.domain.performance_memory import PerformanceDataQuality


def test_performance_data_quality_accepts_valid_assessment() -> None:
    quality = PerformanceDataQuality(
        confidence="HIGH",
        quality_score=Decimal("0.92"),
        snapshot_count=3,
        production_feature_completeness=Decimal("1"),
        metric_completeness=Decimal("0.875"),
        has_baseline=True,
        time_series_point_count=3,
        issues=(),
    )

    assert quality.confidence == "HIGH"
    assert quality.quality_score == Decimal("0.92")
    assert quality.snapshot_count == 3
    assert quality.has_baseline is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("confidence", "UNKNOWN"),
        ("quality_score", Decimal("1.01")),
        ("production_feature_completeness", Decimal("-0.01")),
        ("metric_completeness", Decimal("1.01")),
    ],
)
def test_performance_data_quality_rejects_invalid_ranges(field: str, value: object) -> None:
    kwargs: dict[str, object] = {
        "confidence": "HIGH",
        "quality_score": Decimal("0.8"),
        "snapshot_count": 2,
        "production_feature_completeness": Decimal("0.8"),
        "metric_completeness": Decimal("0.8"),
        "has_baseline": True,
        "time_series_point_count": 2,
        "issues": (),
    }
    kwargs[field] = value

    with pytest.raises(ValueError):
        PerformanceDataQuality(**kwargs)  # type: ignore[arg-type]


def test_performance_data_quality_allows_insufficient_data() -> None:
    quality = PerformanceDataQuality(
        confidence="INSUFFICIENT",
        quality_score=Decimal("0"),
        snapshot_count=0,
        production_feature_completeness=Decimal("0"),
        metric_completeness=Decimal("0"),
        has_baseline=False,
        time_series_point_count=0,
        issues=("NO_PERFORMANCE_SNAPSHOTS", "NO_BASELINE"),
    )

    assert quality.confidence == "INSUFFICIENT"
    assert quality.issues == ("NO_PERFORMANCE_SNAPSHOTS", "NO_BASELINE")
