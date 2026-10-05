from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.topic_optimization import TopicCandidate, TopicEvidence, TopicEvidenceType, TopicScore


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
        metadata = (
            self._value(candidate.relevance_score),
            self._value(candidate.novelty_score),
            self._value(candidate.trend_score),
            self._value(candidate.evergreen_score),
        )
        performance_value = performance.normalized_score if performance is not None else Decimal("0")
        weights = (
            self.policy.relevance_weight,
            self.policy.novelty_weight,
            self.policy.trend_weight,
            self.policy.evergreen_weight,
            self.policy.performance_weight,
        )
        total = sum(
            (value * weight for value, weight in (*metadata, performance_value)),
            Decimal("0"),
        )
        evidence = (
            TopicEvidence(TopicEvidenceType.CANDIDATE_METADATA, self._average(metadata)),
            TopicEvidence(TopicEvidenceType.NOVELTY, self._value(candidate.novelty_score)),
        )
        if performance is not None:
            evidence += (
                TopicEvidence(
                    TopicEvidenceType.HISTORICAL_PERFORMANCE,
                    performance.normalized_score,
                    performance.comparable_observations,
                    performance.confidence,
                ),
            )
        return TopicScore(
            candidate_id=candidate.candidate_id,
            total=total.quantize(Decimal("0.0001")),
            evidence=evidence,
            rationale=self._rationale(candidate, performance),
        )

    @staticmethod
    def _value(value: Decimal | None) -> Decimal:
        return value if value is not None else Decimal("0")

    @staticmethod
    def _average(values: tuple[Decimal, ...]) -> Decimal:
        return sum(values, Decimal("0")) / Decimal(len(values))

    @staticmethod
    def _rationale(
        candidate: TopicCandidate,
        performance: TopicPerformanceEvidence | None,
    ) -> tuple[str, ...]:
        rationale = [
            "Score combines bounded candidate metadata using fixed policy weights.",
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
