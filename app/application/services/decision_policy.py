from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domain.decision import (
    DecisionDimension,
    DecisionPolicy,
    ProductionDecision,
)
from app.domain.learning import (
    ConfidenceLevel,
    Recommendation,
    RecommendationStatus,
    SignalDirection,
)


class DecisionPolicyEngine:
    """Apply eligible learning recommendations through a bounded decision policy."""

    _CONFIDENCE_RANK = {
        ConfidenceLevel.INSUFFICIENT: 0,
        ConfidenceLevel.LOW: 1,
        ConfidenceLevel.MEDIUM: 2,
        ConfidenceLevel.HIGH: 3,
    }
    _DURATION_BUCKET_TARGETS = {
        "<20s": Decimal("18"),
        "20-29s": Decimal("25"),
        "30-39s": Decimal("35"),
        "40-49s": Decimal("45"),
        "50s+": Decimal("50"),
    }

    def __init__(self, policy: DecisionPolicy) -> None:
        self._policy = policy

    def decide(
        self,
        recommendations: Iterable[Recommendation],
        *,
        created_at: datetime | None = None,
    ) -> ProductionDecision:
        candidates: list[tuple[Recommendation, DecisionDimension, str | Decimal]] = []
        rejected: list[UUID] = []
        rationale: list[str] = []

        for recommendation in recommendations:
            candidate = self._candidate(recommendation)
            if candidate is None:
                rejected.append(recommendation.recommendation_id)
                rationale.append(self._rejection_reason(recommendation))
                continue
            candidates.append(candidate)

        winners: dict[DecisionDimension, tuple[Recommendation, str | Decimal]] = {}
        for dimension in self._policy.allowed_dimensions:
            dimension_candidates = [
                candidate
                for candidate in candidates
                if candidate[1] is dimension
            ]
            if not dimension_candidates:
                continue
            winner = max(
                dimension_candidates,
                key=lambda candidate: self._priority_key(candidate[0]),
            )
            winners[dimension] = (winner[0], winner[2])
            rejected.extend(
                recommendation.recommendation_id
                for recommendation, _, _ in dimension_candidates
                if recommendation.recommendation_id != winner[0].recommendation_id
            )
            if len(dimension_candidates) > 1:
                rationale.append(
                    f"Conflict on {dimension}: selected "
                    f"{winner[0].recommendation_id} by confidence, delta magnitude, "
                    "then recommendation ID."
                )

        applied = tuple(
            recommendation.recommendation_id
            for dimension in self._policy.allowed_dimensions
            if dimension in winners
            for recommendation, _ in (winners[dimension],)
        )
        rejected_tuple = tuple(sorted(set(rejected), key=str))
        rationale.extend(
            self._application_reason(recommendation, dimension)
            for dimension, (recommendation, _) in winners.items()
        )

        values = {
            dimension: value for dimension, (_, value) in winners.items()
        }
        return ProductionDecision(
            decision_id=ProductionDecision.empty(
                policy_version=self._policy.policy_version,
                created_at=created_at,
            ).decision_id,
            policy_version=self._policy.policy_version,
            angle=self._optional_value(values, DecisionDimension.ANGLE),
            duration_target_seconds=self._optional_decimal(
                values, DecisionDimension.DURATION_TARGET_SECONDS
            ),
            production_strategy=self._optional_value(
                values, DecisionDimension.PRODUCTION_STRATEGY
            ),
            applied_recommendation_ids=applied,
            rejected_recommendation_ids=rejected_tuple,
            rationale=tuple(rationale),
            created_at=created_at,
        )

    def _candidate(
        self, recommendation: Recommendation
    ) -> tuple[Recommendation, DecisionDimension, str | Decimal] | None:
        signal = recommendation.signal
        if recommendation.status not in {
            RecommendationStatus.GENERATED,
            RecommendationStatus.ACTIVE,
        }:
            return None
        if signal.confidence not in {
            ConfidenceLevel.MEDIUM,
            ConfidenceLevel.HIGH,
        }:
            return None
        if signal.direction is not SignalDirection.POSITIVE:
            return None
        if not signal.evidence.baseline_available or signal.delta is None:
            return None

        dimension, value = self._map_feature(signal.feature, signal.feature_value)
        if dimension not in self._policy.allowed_dimensions:
            return None
        return recommendation, dimension, value

    def _map_feature(
        self, feature: str, feature_value: str
    ) -> tuple[DecisionDimension, str | Decimal]:
        if feature == "angle":
            if not feature_value.strip():
                raise ValueError("angle recommendation value must not be blank")
            return DecisionDimension.ANGLE, feature_value.strip()
        if feature == "duration_bucket":
            try:
                return (
                    DecisionDimension.DURATION_TARGET_SECONDS,
                    self._DURATION_BUCKET_TARGETS[feature_value],
                )
            except KeyError as exc:
                raise ValueError(
                    f"Unsupported duration bucket: {feature_value}"
                ) from exc
        raise ValueError(f"Unsupported learning feature for M10 decisioning: {feature}")

    @classmethod
    def _priority_key(
        cls, recommendation: Recommendation
    ) -> tuple[int, Decimal, str]:
        delta = recommendation.signal.delta or Decimal("0")
        return (
            cls._CONFIDENCE_RANK[recommendation.signal.confidence],
            abs(delta),
            str(recommendation.recommendation_id),
        )

    @staticmethod
    def _optional_value(
        values: dict[DecisionDimension, str | Decimal],
        dimension: DecisionDimension,
    ) -> str | None:
        value = values.get(dimension)
        return value if isinstance(value, str) else None

    @staticmethod
    def _optional_decimal(
        values: dict[DecisionDimension, str | Decimal],
        dimension: DecisionDimension,
    ) -> Decimal | None:
        value = values.get(dimension)
        return value if isinstance(value, Decimal) else None

    @staticmethod
    def _rejection_reason(recommendation: Recommendation) -> str:
        signal = recommendation.signal
        if signal.confidence in {
            ConfidenceLevel.INSUFFICIENT,
            ConfidenceLevel.LOW,
        }:
            return (
                f"Rejected {recommendation.recommendation_id}: confidence "
                f"{signal.confidence.value} is below the policy minimum."
            )
        if signal.direction is SignalDirection.NEGATIVE:
            return (
                f"Rejected {recommendation.recommendation_id}: negative evidence "
                "cannot become a destructive production command."
            )
        if signal.direction is SignalDirection.NEUTRAL:
            return (
                f"Rejected {recommendation.recommendation_id}: neutral evidence "
                "does not justify a production override."
            )
        if not signal.evidence.baseline_available or signal.delta is None:
            return (
                f"Rejected {recommendation.recommendation_id}: comparable baseline "
                "or delta is unavailable."
            )
        if recommendation.status not in {
            RecommendationStatus.GENERATED,
            RecommendationStatus.ACTIVE,
        }:
            return (
                f"Rejected {recommendation.recommendation_id}: recommendation "
                f"status is {recommendation.status.value}."
            )
        return (
            f"Rejected {recommendation.recommendation_id}: feature "
            f"'{signal.feature}' is not supported by the current decision policy."
        )

    @staticmethod
    def _application_reason(
        recommendation: Recommendation, dimension: DecisionDimension
    ) -> str:
        return (
            f"Applied {recommendation.recommendation_id} to {dimension}: "
            f"{recommendation.signal.feature}='{recommendation.signal.feature_value}' "
            f"with {recommendation.signal.confidence.value} confidence and "
            f"delta {recommendation.signal.delta}."
        )
