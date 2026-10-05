from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.decision import ProductionDecision
from app.infrastructure.database.decision_models import ProductionDecisionModel


class DecisionPersistenceService:
    """Persist immutable production decisions idempotently for audit and replay."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, decision: ProductionDecision) -> ProductionDecision:
        existing = self._session.scalar(
            select(ProductionDecisionModel).where(
                ProductionDecisionModel.decision_id == decision.decision_id
            )
        )
        if existing is not None:
            return self.to_decision(existing)

        model = ProductionDecisionModel(
            decision_id=decision.decision_id,
            policy_version=decision.policy_version,
            angle=decision.angle,
            duration_target_seconds=decision.duration_target_seconds,
            production_strategy=decision.production_strategy,
            input_recommendation_ids=[str(item) for item in decision.input_recommendation_ids],
            eligible_recommendation_ids=[
                str(item) for item in decision.eligible_recommendation_ids
            ],
            applied_recommendation_ids=[str(item) for item in decision.applied_recommendation_ids],
            rejected_recommendation_ids=[
                str(item) for item in decision.rejected_recommendation_ids
            ],
            rationale=list(decision.rationale),
            created_at=decision.created_at or datetime.now(UTC),
        )
        self._session.add(model)
        self._session.flush()
        return decision

    @staticmethod
    def to_decision(model: ProductionDecisionModel) -> ProductionDecision:
        return ProductionDecision(
            decision_id=model.decision_id,
            policy_version=model.policy_version,
            angle=model.angle,
            duration_target_seconds=model.duration_target_seconds,
            production_strategy=model.production_strategy,
            input_recommendation_ids=DecisionPersistenceService.parse_uuid_list(
                model.input_recommendation_ids
            ),
            eligible_recommendation_ids=DecisionPersistenceService.parse_uuid_list(
                model.eligible_recommendation_ids
            ),
            applied_recommendation_ids=DecisionPersistenceService.parse_uuid_list(
                model.applied_recommendation_ids
            ),
            rejected_recommendation_ids=DecisionPersistenceService.parse_uuid_list(
                model.rejected_recommendation_ids
            ),
            rationale=tuple(item for item in model.rationale if isinstance(item, str)),
            created_at=model.created_at,
        )

    @staticmethod
    def parse_uuid_list(values: list[object]) -> tuple[UUID, ...]:
        try:
            return tuple(UUID(str(value)) for value in values)
        except (TypeError, ValueError) as exc:
            raise ValueError("decision audit recommendation IDs must be valid UUIDs") from exc
