from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.application.services.decision_persistence import DecisionPersistenceService
from app.domain.decision import ProductionDecision
from app.infrastructure.database.decision_models import ProductionDecisionModel


def _decision() -> ProductionDecision:
    first = uuid4()
    second = uuid4()
    return ProductionDecision(
        decision_id=uuid4(),
        policy_version="m10-v1",
        angle="unexpected fact",
        duration_target_seconds=Decimal("35"),
        input_recommendation_ids=(first, second),
        eligible_recommendation_ids=(first,),
        applied_recommendation_ids=(first,),
        rejected_recommendation_ids=(second,),
        rationale=("Applied high-confidence angle.",),
        created_at=datetime(2026, 10, 5, 13, tzinfo=UTC),
    )


def _model_from_decision(decision: ProductionDecision) -> ProductionDecisionModel:
    return ProductionDecisionModel(
        decision_id=decision.decision_id,
        policy_version=decision.policy_version,
        angle=decision.angle,
        duration_target_seconds=decision.duration_target_seconds,
        production_strategy=decision.production_strategy,
        input_recommendation_ids=[str(item) for item in decision.input_recommendation_ids],
        eligible_recommendation_ids=[str(item) for item in decision.eligible_recommendation_ids],
        applied_recommendation_ids=[str(item) for item in decision.applied_recommendation_ids],
        rejected_recommendation_ids=[str(item) for item in decision.rejected_recommendation_ids],
        rationale=list(decision.rationale),
        created_at=decision.created_at,
    )


def test_save_persists_complete_decision_audit() -> None:
    session = MagicMock()
    session.scalar.return_value = None
    decision = _decision()

    result = DecisionPersistenceService(session).save(decision)

    assert result == decision
    model = session.add.call_args.args[0]
    assert isinstance(model, ProductionDecisionModel)
    assert model.decision_id == decision.decision_id
    assert model.policy_version == "m10-v1"
    assert model.input_recommendation_ids == [str(item) for item in decision.input_recommendation_ids]
    assert model.eligible_recommendation_ids == [
        str(item) for item in decision.eligible_recommendation_ids
    ]
    assert model.applied_recommendation_ids == [
        str(item) for item in decision.applied_recommendation_ids
    ]
    assert model.rejected_recommendation_ids == [
        str(item) for item in decision.rejected_recommendation_ids
    ]
    assert model.rationale == list(decision.rationale)
    session.flush.assert_called_once()


def test_save_is_idempotent_for_existing_decision() -> None:
    session = MagicMock()
    decision = _decision()
    session.scalar.return_value = _model_from_decision(decision)

    result = DecisionPersistenceService(session).save(decision)

    assert result == decision
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_to_decision_roundtrips_audit_ids() -> None:
    decision = _decision()
    model = _model_from_decision(decision)

    result = DecisionPersistenceService.to_decision(model)

    assert result == decision


def test_parse_uuid_list_rejects_invalid_ids() -> None:
    with pytest.raises(ValueError, match="valid UUIDs"):
        DecisionPersistenceService.parse_uuid_list(["not-a-uuid"])
