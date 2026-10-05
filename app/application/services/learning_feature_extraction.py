from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from app.domain.learning_features import FeatureObservation, LearningFeature, duration_bucket
from app.domain.performance_memory import PerformanceQueryResult


class LearningFeatureExtractionService:
    """Extract deterministic feature cohorts from M8 performance query results."""

    _METRICS = (
        "views",
        "average_view_duration_seconds",
        "retention",
    )

    def extract(
        self,
        results: Iterable[PerformanceQueryResult],
    ) -> tuple[FeatureObservation, ...]:
        grouped: dict[tuple[LearningFeature, str, str], list[Decimal]] = defaultdict(list)

        for result in results:
            point = result.time_series[-1]
            features = result.memory.features

            feature_values = (
                (LearningFeature.CATEGORY, features.category),
                (LearningFeature.ANGLE, features.angle),
                (LearningFeature.DURATION_BUCKET, duration_bucket(features.duration_target_seconds)),
                (LearningFeature.TOPIC, features.topic),
            )

            metrics = (
                ("views", Decimal(point.views)),
                ("average_view_duration_seconds", point.average_view_duration_seconds),
                ("retention", point.retention),
            )

            for feature, feature_value in feature_values:
                if feature_value is None:
                    continue
                for metric, value in metrics:
                    if value is not None:
                        grouped[(feature, feature_value, metric)].append(value)

        observations = []
        for (feature, feature_value, metric), values in sorted(
            grouped.items(),
            key=lambda item: (
                item[0][0].value,
                item[0][1],
                item[0][2],
            ),
        ):
            observations.append(
                FeatureObservation(
                    feature=feature,
                    feature_value=feature_value,
                    metric=metric,
                    observed_value=sum(values, Decimal("0")) / Decimal(len(values)),
                    sample_size=len(values),
                )
            )

        return tuple(observations)
