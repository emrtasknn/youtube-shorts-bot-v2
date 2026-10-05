from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from app.domain.learning import (
    ConfidenceLevel,
    LearningEvidence,
    LearningSignal,
    SignalDirection,
)
from app.domain.learning_features import FeatureObservation, LearningFeature
from app.domain.performance_memory import PerformanceBaseline, PerformanceQueryResult


class LearningEvidenceService:
    """Build deterministic learning signals from feature observations and M8 evidence."""

    def evaluate(
        self,
        observations: Iterable[FeatureObservation],
        results: Iterable[PerformanceQueryResult],
        *,
        created_at: datetime,
    ) -> tuple[LearningSignal, ...]:
        materialized_results = tuple(results)
        signals = [
            self._build_signal(observation, materialized_results, created_at=created_at)
            for observation in observations
        ]
        return tuple(
            sorted(
                signals,
                key=lambda signal: (
                    signal.feature,
                    signal.feature_value,
                    signal.metric,
                ),
            )
        )

    def _build_signal(
        self,
        observation: FeatureObservation,
        results: tuple[PerformanceQueryResult, ...],
        *,
        created_at: datetime,
    ) -> LearningSignal:
        matching = tuple(
            result
            for result in results
            if self._feature_value(result, observation.feature) == observation.feature_value
            and self._metric_value(result, observation.metric) is not None
        )
        baseline_value, baseline_available, baseline_note = self._baseline(
            observation,
            matching,
        )
        quality_score = self._quality_score(matching)
        confidence = self._confidence(observation.sample_size, quality_score)
        delta = observation.observed_value - baseline_value if baseline_value is not None else None
        direction = self._direction(delta)
        notes = [baseline_note]
        if quality_score is None:
            notes.append("performance data quality is unavailable")
        elif quality_score < Decimal("1"):
            notes.append("signal evidence includes less-than-perfect data quality")
        if observation.sample_size <= 2:
            notes.append("sample-size policy classifies fewer than 3 observations as insufficient")
        return LearningSignal(
            signal_id=uuid5(
                NAMESPACE_URL,
                f"learning:{observation.feature.value}:{observation.feature_value}:{observation.metric}",
            ),
            feature=observation.feature.value,
            feature_value=observation.feature_value,
            metric=observation.metric,
            observed_value=observation.observed_value,
            baseline_value=baseline_value,
            delta=delta,
            evidence=LearningEvidence(
                sample_size=observation.sample_size,
                baseline_available=baseline_available,
                data_quality_score=quality_score or Decimal("0"),
                notes=tuple(notes),
            ),
            confidence=confidence,
            direction=direction,
            created_at=created_at,
        )

    @staticmethod
    def _feature_value(
        result: PerformanceQueryResult,
        feature: LearningFeature,
    ) -> str | None:
        features = result.memory.features
        if feature is LearningFeature.CATEGORY:
            return features.category
        if feature is LearningFeature.ANGLE:
            return features.angle
        if feature is LearningFeature.DURATION_BUCKET:
            from app.domain.learning_features import duration_bucket

            return duration_bucket(features.duration_target_seconds)
        return features.topic

    @staticmethod
    def _metric_value(
        result: PerformanceQueryResult,
        metric: str,
    ) -> Decimal | None:
        point = result.time_series[-1]
        if metric == "views":
            return Decimal(point.views)
        if metric == "average_view_duration_seconds":
            return point.average_view_duration_seconds
        if metric == "retention":
            return point.retention
        return None

    @staticmethod
    def _baseline(
        observation: FeatureObservation,
        results: tuple[PerformanceQueryResult, ...],
    ) -> tuple[Decimal | None, bool, str]:
        if observation.feature is LearningFeature.CATEGORY:
            return (
                None,
                False,
                "category baseline is intentionally unavailable because M8 baseline is category-scoped",
            )

        baselines = [
            result.baseline
            for result in results
            if result.baseline is not None
            and LearningEvidenceService._baseline_metric(result.baseline, observation.metric)
            is not None
        ]
        if not baselines:
            return None, False, "baseline unavailable for this feature cohort"

        cohorts = {
            (baseline.category, baseline.language, baseline.production_strategy)
            for baseline in baselines
        }
        if len(cohorts) != 1:
            return (
                None,
                False,
                "baseline unavailable because contributing publications use mixed baseline cohorts",
            )

        values = [
            LearningEvidenceService._baseline_metric(baseline, observation.metric)
            for baseline in baselines
        ]
        return (
            sum((value for value in values if value is not None), Decimal("0"))
            / Decimal(len(values)),
            True,
            "baseline is the M8 category/language/production-strategy cohort average",
        )

    @staticmethod
    def _baseline_metric(baseline: PerformanceBaseline, metric: str) -> Decimal | None:
        if metric == "views":
            return baseline.average_views
        if metric == "average_view_duration_seconds":
            return baseline.average_view_duration_seconds
        if metric == "retention":
            return baseline.average_retention
        return None

    @staticmethod
    def _quality_score(results: tuple[PerformanceQueryResult, ...]) -> Decimal | None:
        scores = [result.quality.quality_score for result in results if result.quality is not None]
        if not scores:
            return None
        return min(scores)

    @staticmethod
    def _confidence(sample_size: int, quality_score: Decimal | None) -> ConfidenceLevel:
        if sample_size <= 2:
            return ConfidenceLevel.INSUFFICIENT
        if sample_size <= 5:
            level = ConfidenceLevel.LOW
        elif sample_size <= 14:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.HIGH
        if quality_score is not None and quality_score == 0:
            return ConfidenceLevel.INSUFFICIENT
        return level

    @staticmethod
    def _direction(delta: Decimal | None) -> SignalDirection:
        if delta is None or delta == 0:
            return SignalDirection.NEUTRAL
        return SignalDirection.POSITIVE if delta > 0 else SignalDirection.NEGATIVE
