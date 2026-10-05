from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.services.topic_selection import (
    TopicSelectionPolicy,
    TopicSelectionService,
)
from app.domain.topic_optimization import (
    TopicCandidate,
    TopicDecisionStatus,
    TopicEvidence,
    TopicEvidenceType,
    TopicScore,
)


def candidate(candidate_id: UUID, title: str = "Topic") -> TopicCandidate:
    return TopicCandidate(
        candidate_id=candidate_id,
        title=title,
        source="research",
        relevance_score=Decimal("0.8"),
        novelty_score=Decimal("0.8"),
        trend_score=Decimal("0.7"),
        evergreen_score=Decimal("0.7"),
    )


def score(
    candidate_id: UUID,
    total: str,
    novelty: str = "0.5",
) -> TopicScore:
    return TopicScore(
        candidate_id=candidate_id,
        total=Decimal(total),
        evidence=(
            TopicEvidence(
                evidence_type=TopicEvidenceType.NOVELTY,
                value=Decimal(novelty),
            ),
        ),
    )


def test_policy_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        TopicSelectionPolicy(minimum_score=Decimal("1.1"))


def test_selects_highest_scoring_eligible_candidate() -> None:
    first_id = uuid4()
    second_id = uuid4()

    decision = TopicSelectionService().select(
        (candidate(first_id, "First"), candidate(second_id, "Second")),
        (score(first_id, "0.61"), score(second_id, "0.91")),
    )

    assert decision.status is TopicDecisionStatus.SELECTED
    assert decision.selected_candidate_id == second_id
    assert decision.selected_topic == "Second"
    assert decision.selected_score is not None
    assert decision.selected_score.total == Decimal("0.91")


def test_rejects_candidates_below_minimum_score() -> None:
    candidate_id = uuid4()

    decision = TopicSelectionService().select(
        (candidate(candidate_id),),
        (score(candidate_id, "0.59"),),
    )

    assert decision.status is TopicDecisionStatus.NO_SELECTION
    assert decision.selected_candidate_id is None
    assert candidate_id in decision.candidate_ids


def test_missing_score_cannot_be_selected() -> None:
    candidate_id = uuid4()

    decision = TopicSelectionService().select(
        (candidate(candidate_id),),
        (),
    )

    assert decision.status is TopicDecisionStatus.NO_SELECTION


def test_equal_scores_use_novelty_as_tie_break() -> None:
    first_id = UUID("00000000-0000-0000-0000-000000000001")
    second_id = UUID("00000000-0000-0000-0000-000000000002")

    decision = TopicSelectionService().select(
        (candidate(first_id), candidate(second_id)),
        (
            score(first_id, "0.80", "0.60"),
            score(second_id, "0.80", "0.90"),
        ),
    )

    assert decision.selected_candidate_id == second_id


def test_equal_score_and_novelty_uses_deterministic_candidate_id() -> None:
    first_id = UUID("00000000-0000-0000-0000-000000000001")
    second_id = UUID("00000000-0000-0000-0000-000000000002")

    decision = TopicSelectionService().select(
        (candidate(second_id), candidate(first_id)),
        (
            score(second_id, "0.80", "0.80"),
            score(first_id, "0.80", "0.80"),
        ),
    )

    assert decision.selected_candidate_id == first_id


def test_candidate_ids_are_returned_in_deterministic_order() -> None:
    first_id = UUID("00000000-0000-0000-0000-000000000001")
    second_id = UUID("00000000-0000-0000-0000-000000000002")

    decision = TopicSelectionService().select(
        (candidate(second_id), candidate(first_id)),
        (),
    )

    assert decision.candidate_ids == (first_id, second_id)


def test_selection_is_explainable() -> None:
    candidate_id = uuid4()

    decision = TopicSelectionService().select(
        (candidate(candidate_id),),
        (score(candidate_id, "0.75"),),
    )

    assert decision.rationale
    assert all(item.strip() for item in decision.rationale)


def test_same_inputs_produce_same_decision_id() -> None:
    candidate_id = UUID("00000000-0000-0000-0000-000000000001")
    candidates = (candidate(candidate_id, "Same"),)
    scores = (score(candidate_id, "0.75", "0.80"),)

    first = TopicSelectionService().select(candidates, scores)
    second = TopicSelectionService().select(candidates, scores)

    assert first.decision_id == second.decision_id


def test_duplicate_candidate_ids_are_rejected() -> None:
    candidate_id = uuid4()

    with pytest.raises(ValueError, match="candidate IDs"):
        TopicSelectionService().select(
            (candidate(candidate_id), candidate(candidate_id, "Duplicate")),
            (score(candidate_id, "0.80"),),
        )


def test_duplicate_scores_are_rejected() -> None:
    candidate_id = uuid4()

    with pytest.raises(ValueError, match="topic scores"):
        TopicSelectionService().select(
            (candidate(candidate_id),),
            (score(candidate_id, "0.80"), score(candidate_id, "0.80")),
        )
