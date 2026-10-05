from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from app.application.services.topic_selection_persistence import (
    TopicSelectionPersistenceService,
)
from app.domain.topic_optimization import (
    TopicDecisionStatus,
    TopicEvidence,
    TopicEvidenceType,
    TopicScore,
    TopicSelectionDecision,
)
from app.infrastructure.database.models import TopicSelectionDecisionModel


def _score(candidate_id: UUID) -> TopicScore:
    return TopicScore(
        candidate_id=candidate_id,
        total=Decimal("0.82"),
        evidence=(
            TopicEvidence(
                evidence_type=TopicEvidenceType.NOVELTY,
                value=Decimal("0.9"),
                sample_size=4,
                confidence=Decimal("0.75"),
            ),
        ),
        rationale=("Novelty evidence supports selection.",),
    )


def _decision() -> TopicSelectionDecision:
    first = UUID("00000000-0000-0000-0000-000000000001")
    second = UUID("00000000-0000-0000-0000-000000000002")
    return TopicSelectionDecision(
        decision_id=UUID("10000000-0000-0000-0000-000000000001"),
        status=TopicDecisionStatus.SELECTED,
        selected_candidate_id=first,
        selected_topic="A forgotten empire",
        candidate_ids=(first, second),
        selected_score=_score(first),
        rationale=("Selected highest-scoring eligible candidate.",),
    )


def _model_from_decision(decision: TopicSelectionDecision) -> TopicSelectionDecisionModel:
    return TopicSelectionDecisionModel(
        decision_id=decision.decision_id,
        status=decision.status.value,
        selected_candidate_id=decision.selected_candidate_id,
        selected_topic=decision.selected_topic,
        candidate_ids=[str(item) for item in decision.candidate_ids],
        selected_score=TopicSelectionPersistenceService._score_to_payload(
            decision.selected_score
        ),
        rationale=list(decision.rationale),
    )


def test_save_persists_complete_selection_audit() -> None:
    session = MagicMock()
    session.scalar.return_value = None
    decision = _decision()

    result = TopicSelectionPersistenceService(session).save(decision)

    assert result == decision
    model = session.add.call_args.args[0]
    assert isinstance(model, TopicSelectionDecisionModel)
    assert model.decision_id == decision.decision_id
    assert model.status == "selected"
    assert model.selected_candidate_id == decision.selected_candidate_id
    assert model.candidate_ids == [str(item) for item in decision.candidate_ids]
    assert model.selected_score["total"] == "0.82"
    assert model.selected_score["evidence"][0]["sample_size"] == 4
    assert model.rationale == list(decision.rationale)
    session.flush.assert_called_once()


def test_save_is_idempotent_for_existing_decision() -> None:
    session = MagicMock()
    decision = _decision()
    session.scalar.return_value = _model_from_decision(decision)

    result = TopicSelectionPersistenceService(session).save(decision)

    assert result == decision
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_to_decision_roundtrips_complete_score_audit() -> None:
    decision = _decision()
    model = _model_from_decision(decision)

    result = TopicSelectionPersistenceService.to_decision(model)

    assert result == decision


def test_no_selection_roundtrips_without_score() -> None:
    decision = TopicSelectionDecision.no_selection(
        decision_id=UUID("20000000-0000-0000-0000-000000000001"),
        candidate_ids=(UUID("00000000-0000-0000-0000-000000000001"),),
        rationale=("No candidate reached the threshold.",),
    )
    model = _model_from_decision(decision)

    result = TopicSelectionPersistenceService.to_decision(model)

    assert result == decision
    assert model.selected_score is None


def test_parse_uuid_list_rejects_invalid_ids() -> None:
    with pytest.raises(ValueError, match="valid UUIDs"):
        TopicSelectionPersistenceService._parse_uuid_list(["not-a-uuid"])


def test_payload_to_score_rejects_invalid_score() -> None:
    with pytest.raises((KeyError, ValueError)):
        TopicSelectionPersistenceService._payload_to_score({"candidate_id": "not-a-uuid"})
