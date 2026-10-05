from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.topic_optimization import (
    TopicCandidate,
    TopicEvidence,
    TopicEvidenceType,
    TopicScore,
)


@dataclass(frozen=True, slots=True)
class TopicScoringPolicy:
    """Fixed, explainable weights for deterministic topic scoring."""

    relevance_weight: Decimal = Decimal("0.30")
    novelty_weight: Decimal = Decimal("0.30")
    trend_weight: Decimal = Decimal("0.15")
    evergreen_weight: Decimal = Decimal("0.10")
    performance_weight: Decimal = Decimal("0.15")

    def __post_init__(self) -> None:
        weights = (
            self.relevance_weight,
            self.novelty_weight,
            self.trend_weight,
            self.evergreen_weight,
            self.performance_weight,
        )
        if any(weight < 0 for weight in weights):
            raise ValueError("topic scoring weights must be non-negative")
        if sum(weights, Decimal("0")) != Decimal("1"):
            raise ValueError("topic scoring weights must sum to 1")


@dataclass(frozen=True, slots=True)
class TopicPerformanceEvidence:
    """Comparable historical performance supplied by the performance layer."""

    normalized_score: Decimal
    comparable_observations: int
    confidence: Decimal

    def __post_init__(self) -> None:
        if not 0 <= self.normalized_score <= 1:
            raise ValueError("normalized performance score must be between 0 and 1")
        if self.comparable_observations < 0:
            raise ValueError("comparable observations must be non-negative")
        if not 0 <= self.confidence <= 1:
            raise ValueError("performance confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class TopicScoringService:
    """Score supplied candidates without generating or mutating topics."""

    policy: TopicScoringPolicy = TopicScoringPolicy()

    def score(
        self,
        candidate: TopicCandidate,
        *,
        performance: TopicPerformanceEvidence | None = None,
    ) -> TopicScore:
        components = (
            ("relevance", candidate.relevance_score, self.policy.relevance_weight),
            ("novelty", candidate.novelty_score, self.policy.novelty_weight),
            ("trend", candidate.trend_score, self.policy.trend_weight),
            ("evergreen", candidate.evergreen_score, self.policy.evergreen_weight),
        )
        available = [
            (name, value, weight)
            for name, value, weight in components
            if value is not None
        ]
        if performance is not None and performance.comparable_observations > 0:
            available.append(
                (
                    "performance",
                    performance.normalized_score,
                    self.policy.performance_weight,
                )
            )

        total_weight = sum((weight for _, _, weight in available), Decimal("0"))
        total = (
            sum((value * weight for _, value, weight in available), Decimal("0"))
            / total_weight
            if total_weight
            else Decimal("0")
        )

        evidence = tuple(
            TopicEvidence(
                TopicEvidenceType.HISTORICAL_PERFORMANCE
                if name == "performance"
                else (
                    TopicEvidenceType.NOVELTY
                    if name == "novelty"
                    else TopicEvidenceType.CANDIDATE_METADATA
                ),
                value,
                performance.comparable_observations
                if name == "performance" and performance
                else 0,
                performance.confidence
                if name == "performance" and performance
                else Decimal("0"),
            )
            for name, value, _ in available
        )
        return TopicScore(
            candidate_id=candidate.candidate_id,
            total=total.quantize(Decimal("0.0001")),
            evidence=evidence,
            rationale=self._rationale(candidate, performance),
        )

    @staticmethod
    def _rationale(
        candidate: TopicCandidate,
        performance: TopicPerformanceEvidence | None,
    ) -> tuple[str, ...]:
        rationale = [
            "Score combines available bounded signals using fixed policy weights.",
        ]
        if candidate.novelty_score is not None:
            rationale.append("Novelty is included explicitly.")
        if performance is None or performance.comparable_observations == 0:
            rationale.append("Historical performance is unavailable; no historical signal is used.")
        else:
            rationale.append(
                f"Historical performance uses {performance.comparable_observations} comparable observations."
            )
        return tuple(rationale)
