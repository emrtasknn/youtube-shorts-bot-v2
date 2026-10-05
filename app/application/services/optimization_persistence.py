from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.experimentation import ExperimentDimension
from app.domain.learning import ConfidenceLevel
from app.domain.optimization import OptimizationDecision, OptimizationDecisionStatus
from app.infrastructure.database.models import OptimizationDecisionModel


@dataclass(frozen=True, slots=True)
class OptimizationDecisionPersistenceService:
    session: Session

    def save(self, decision: OptimizationDecision) -> OptimizationDecision:
        existing = self.session.scalar(
            select(OptimizationDecisionModel).where(
                OptimizationDecisionModel.decision_id == decision.decision_id
            )
        )
        if existing is not None:
            current = self.to_decision(existing)
            if current != decision:
                raise ValueError("existing optimization decision conflicts with supplied decision")
            return current

        model = OptimizationDecisionModel(
            decision_id=decision.decision_id,
            policy_version=decision.policy_version,
            status=decision.status.value,
            experiment_id=decision.experiment_id,
            dimension=decision.dimension.value if decision.dimension else None,
            winner_variant_id=decision.winner_variant_id,
            value=decision.value,
            control_variant_id=decision.control_variant_id,
            uplift=decision.uplift,
            confidence=decision.confidence.value,
            rationale=list(decision.rationale),
            created_at=decision.created_at or datetime.now(UTC),
        )
        self.session.add(model)
        self.session.flush()
        return decision

    @staticmethod
    def to_decision(model: OptimizationDecisionModel) -> OptimizationDecision:
        return OptimizationDecision(
            decision_id=model.decision_id,
            policy_version=model.policy_version,
            status=OptimizationDecisionStatus(model.status),
            experiment_id=model.experiment_id,
            dimension=ExperimentDimension(model.dimension) if model.dimension else None,
            winner_variant_id=model.winner_variant_id,
            value=model.value,
            control_variant_id=model.control_variant_id,
            uplift=Decimal(str(model.uplift)) if model.uplift is not None else None,
            confidence=ConfidenceLevel(model.confidence),
            rationale=tuple(item for item in model.rationale if isinstance(item, str)),
        )
