from __future__ import annotations

from decimal import Decimal

from app.domain.performance_memory import PerformanceDataQuality, PerformanceQueryResult

_REQUIRED_PRODUCTION_FIELDS = (
    "category",
    "language",
    "topic",
    "hook",
    "scene_count",
    "visual_providers",
    "production_strategy",
)
_OPTIONAL_METRIC_FIELDS = (
    "average_view_duration_seconds",
    "retention",
)


class PerformanceDataQualityService:
    """Evaluate deterministic completeness and confidence for performance memory."""

    def evaluate(self, result: PerformanceQueryResult) -> PerformanceDataQuality:
        memory = result.memory
        features = memory.features
        production_values = {
            "category": features.category,
            "language": features.language,
            "topic": features.topic,
            "hook": features.hook,
            "scene_count": features.scene_count,
            "visual_providers": features.visual_providers,
            "production_strategy": features.production_strategy,
        }

        production_present = sum(
            value is not None and value != "" and value != ()
            for value in production_values.values()
        )
        production_completeness = Decimal(production_present) / Decimal(
            len(_REQUIRED_PRODUCTION_FIELDS)
        )

        metric_present = Decimal(5)
        metric_total = Decimal(5 + len(_OPTIONAL_METRIC_FIELDS))
        for point in result.time_series:
            metric_present += sum(
                getattr(point, field) is not None for field in _OPTIONAL_METRIC_FIELDS
            )
        metric_completeness = metric_present / (
            metric_total * Decimal(len(result.time_series))
        )

        issues: list[str] = []
        if not result.time_series:
            issues.append("NO_TIME_SERIES")
        if result.baseline is None:
            issues.append("NO_BASELINE")
        if production_completeness < 1:
            issues.append("INCOMPLETE_PRODUCTION_FEATURES")
        if metric_completeness < 1:
            issues.append("INCOMPLETE_OPTIONAL_METRICS")

        snapshot_count = len(result.time_series)
        if snapshot_count == 0:
            confidence = "INSUFFICIENT"
        elif snapshot_count == 1 or result.baseline is None:
            confidence = "LOW"
        elif production_completeness < 1 or metric_completeness < 1:
            confidence = "MEDIUM"
        else:
            confidence = "HIGH"

        quality_score = (
            production_completeness * Decimal("0.4")
            + metric_completeness * Decimal("0.4")
            + (Decimal("0.2") if result.baseline is not None else Decimal("0"))
        )

        return PerformanceDataQuality(
            confidence=confidence,
            quality_score=quality_score,
            snapshot_count=snapshot_count,
            production_feature_completeness=production_completeness,
            metric_completeness=metric_completeness,
            has_baseline=result.baseline is not None,
            time_series_point_count=snapshot_count,
            issues=tuple(issues),
        )
