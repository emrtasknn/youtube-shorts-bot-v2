from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.services.topic_scoring import (
    TopicPerformanceEvidence,
    TopicScoringPolicy,
    TopicScoringService,
)
from app.domain.topic_optimization import TopicCandidate, TopicEvidenceType


def candidate(**overrides: object) -> TopicCandidate:
    values: dict[str, object] = {
        "candidate_id": uuid4(),
        "title": "A history topic",
        "source": "research",
        "relevance_score": Decimal("0.8"),
        "novelty_score": Decimal("0.9"),
        "trend_score": Decimal("0.6"),
        "evergreen_score": Decimal("0.7"),
    }
    values.update(overrides)
    return TopicCandidate(**values)


def test_policy_weights_are_fixed_and_sum_to_one() -> None:
    policy = TopicScoringPolicy()

    assert sum(
        (
            policy.relevance_weight,
            policy.novelty_weight,
            policy.trend_weight,
            policy.evergreen_weight,
            policy.performance_weight,
        ),
        Decimal("0"),
    ) == Decimal("1")


def test_policy_rejects_invalid_weights() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        TopicScoringPolicy(relevance_weight=Decimal("0.5"))


def test_scoring_is_deterministic() -> None:
    service = TopicScoringService()
    topic = candidate()
    first = service.score(topic)
    second = service.score(topic)

    assert first == second


def test_scoring_is_bounded_and_explainable_without_performance() -> None:
    score = TopicScoringService().score(candidate())

    assert Decimal("0") <= score.total <= Decimal("1")
    assert TopicEvidenceType.NOVELTY in {item.evidence_type for item in score.evidence}
    assert any("no historical signal" in item for item in score.rationale)


def test_comparable_performance_is_included() -> None:
    score = TopicScoringService().score(
        candidate(),
        performance=TopicPerformanceEvidence(
            normalized_score=Decimal("0.8"),
            comparable_observations=12,
            confidence=Decimal("0.9"),
        ),
    )

    assert any(
        item.evidence_type is TopicEvidenceType.HISTORICAL_PERFORMANCE
        for item in score.evidence
    )
    assert any("12 comparable observations" in item for item in score.rationale)


def test_missing_candidate_metadata_is_cold_start_safe() -> None:
    score = TopicScoringService().score(
        candidate(
            relevance_score=None,
            novelty_score=None,
            trend_score=None,
            evergreen_score=None,
        )
    )

    assert score.total == Decimal("0.0000")


def test_performance_requires_normalized_bounded_input() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        TopicPerformanceEvidence(
            normalized_score=Decimal("1.1"),
            comparable_observations=1,
            confidence=Decimal("0.5"),
        )
