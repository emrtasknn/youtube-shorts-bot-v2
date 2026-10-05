from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.domain.topic_optimization import (
    TopicCandidate,
    TopicDecisionStatus,
    TopicEvidence,
    TopicEvidenceType,
    TopicScore,
    TopicSelectionDecision,
)


def test_topic_candidate_accepts_bounded_metadata_scores() -> None:
    candidate = TopicCandidate(
        candidate_id=uuid4(),
        title="The fall of a forgotten empire",
        source="research",
        relevance_score=Decimal("0.9"),
        novelty_score=Decimal("0.8"),
        trend_score=Decimal("0.7"),
        evergreen_score=Decimal("0.6"),
    )

    assert candidate.title
    assert candidate.relevance_score == Decimal("0.9")


@pytest.mark.parametrize(
    "field",
    ["relevance_score", "novelty_score", "trend_score", "evergreen_score"],
)
def test_topic_candidate_rejects_out_of_range_scores(field: str) -> None:
    values = {field: Decimal("1.1")}
    with pytest.raises(ValueError, match="between 0 and 1"):
        TopicCandidate(
            candidate_id=uuid4(),
            title="Topic",
            source="research",
            **values,
        )


def test_topic_evidence_is_bounded_and_confidence_aware() -> None:
    evidence = TopicEvidence(
        evidence_type=TopicEvidenceType.HISTORICAL_PERFORMANCE,
        value=Decimal("0.8"),
        sample_size=12,
        confidence=Decimal("0.75"),
    )

    assert evidence.sample_size == 12


def test_topic_score_is_explainable() -> None:
    score = TopicScore(
        candidate_id=uuid4(),
        total=Decimal("0.82"),
        evidence=(
            TopicEvidence(
                evidence_type=TopicEvidenceType.CANDIDATE_METADATA,
                value=Decimal("0.82"),
            ),
        ),
        rationale=("Candidate metadata supports selection.",),
    )

    assert score.total == Decimal("0.82")
    assert score.rationale


def test_selected_decision_requires_selection_contract() -> None:
    candidate_id = uuid4()
    score = TopicScore(candidate_id=candidate_id, total=Decimal("0.9"))

    decision = TopicSelectionDecision(
        decision_id=uuid4(),
        status=TopicDecisionStatus.SELECTED,
        selected_candidate_id=candidate_id,
        selected_topic="A topic",
        selected_score=score,
    )

    assert decision.selected_candidate_id == candidate_id


def test_no_selection_is_safe_default() -> None:
    decision = TopicSelectionDecision.no_selection(
        rationale=("No candidate has sufficient evidence.",),
    )

    assert decision.status is TopicDecisionStatus.NO_SELECTION
    assert decision.selected_candidate_id is None


def test_selected_decision_rejects_missing_score() -> None:
    with pytest.raises(ValueError, match="require a score"):
        TopicSelectionDecision(
            decision_id=uuid4(),
            status=TopicDecisionStatus.SELECTED,
            selected_candidate_id=uuid4(),
            selected_topic="A topic",
        )


def test_selected_decision_rejects_score_for_different_candidate() -> None:
    candidate_id = uuid4()
    with pytest.raises(ValueError, match="selected score"):
        TopicSelectionDecision(
            decision_id=uuid4(),
            status=TopicDecisionStatus.SELECTED,
            selected_candidate_id=candidate_id,
            selected_topic="A topic",
            candidate_ids=(candidate_id,),
            selected_score=TopicScore(
                candidate_id=uuid4(),
                total=Decimal("0.9"),
            ),
        )


def test_selected_decision_requires_selected_candidate_in_candidate_ids() -> None:
    candidate_id = uuid4()
    with pytest.raises(ValueError, match="candidate_ids"):
        TopicSelectionDecision(
            decision_id=uuid4(),
            status=TopicDecisionStatus.SELECTED,
            selected_candidate_id=candidate_id,
            selected_topic="A topic",
            candidate_ids=(uuid4(),),
            selected_score=TopicScore(
                candidate_id=candidate_id,
                total=Decimal("0.9"),
            ),
        )


def test_no_selection_accepts_deterministic_decision_id() -> None:
    decision_id = UUID("00000000-0000-0000-0000-000000000001")
    decision = TopicSelectionDecision.no_selection(decision_id=decision_id)
    assert decision.decision_id == decision_id
