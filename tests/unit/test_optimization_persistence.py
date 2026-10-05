from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.application.services.optimization_persistence import OptimizationDecisionPersistenceService
from app.domain.learning import ConfidenceLevel
from app.domain.optimization import OptimizationDecision, OptimizationDecisionStatus
from app.infrastructure.database.models import OptimizationDecisionModel


def _decision() -> OptimizationDecision:
    return OptimizationDecision.no_promotion(
        experiment_id=UUID("00000000-0000-0000-0000-000000000802"),
        policy_version="m13-v1",
        rationale=("no promotion",),
        decision_id=UUID("00000000-0000-0000-0000-000000000801"),
    )


def test_no_promotion_round_trip() -> None:
    decision = _decision()
    model = OptimizationDecisionModel(
        id=UUID("00000000-0000-0000-0000-000000000803"),
        decision_id=decision.decision_id,
        policy_version=decision.policy_version,
        status="NO_PROMOTION",
        experiment_id=decision.experiment_id,
        confidence=ConfidenceLevel.INSUFFICIENT.value,
        rationale=list(decision.rationale),
    )
    restored = OptimizationDecisionPersistenceService.to_decision(model)
    assert restored.status is OptimizationDecisionStatus.NO_PROMOTION


def test_conflicting_existing_decision_is_rejected() -> None:
    decision = _decision()
    existing = OptimizationDecisionModel(
        id=UUID("00000000-0000-0000-0000-000000000805"),
        decision_id=decision.decision_id,
        policy_version="different",
        status="NO_PROMOTION",
        experiment_id=decision.experiment_id,
        confidence=ConfidenceLevel.INSUFFICIENT.value,
        rationale=["existing"],
    )
    session = MagicMock()
    session.scalar.return_value = existing

    with pytest.raises(ValueError, match="conflicts"):
        OptimizationDecisionPersistenceService(session).save(decision)
