from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.topic_optimization import (
    TopicDecisionStatus,
    TopicEvidence,
    TopicEvidenceType,
    TopicScore,
    TopicSelectionDecision,
)
from app.infrastructure.database.models import TopicSelectionDecisionModel


class TopicSelectionPersistenceService:
    """Persist topic selection decisions idempotently for audit and replay."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, decision: TopicSelectionDecision) -> TopicSelectionDecision:
        existing = self._session.scalar(
            select(TopicSelectionDecisionModel).where(
                TopicSelectionDecisionModel.decision_id == decision.decision_id
            )
        )
        if existing is not None:
            return self.to_decision(existing)

        model = TopicSelectionDecisionModel(
            decision_id=decision.decision_id,
            status=decision.status.value,
            selected_candidate_id=decision.selected_candidate_id,
            selected_topic=decision.selected_topic,
            candidate_ids=[str(item) for item in decision.candidate_ids],
            selected_score=self._score_to_payload(decision.selected_score),
            rationale=list(decision.rationale),
        )
        self._session.add(model)
        self._session.flush()
        return decision

    @staticmethod
    def to_decision(model: TopicSelectionDecisionModel) -> TopicSelectionDecision:
        selected_score = (
            TopicSelectionPersistenceService._payload_to_score(model.selected_score)
            if model.selected_score is not None
            else None
        )
        return TopicSelectionDecision(
            decision_id=model.decision_id,
            status=TopicDecisionStatus(model.status),
            selected_candidate_id=model.selected_candidate_id,
            selected_topic=model.selected_topic,
            candidate_ids=TopicSelectionPersistenceService._parse_uuid_list(model.candidate_ids),
            selected_score=selected_score,
            rationale=tuple(item for item in model.rationale if isinstance(item, str)),
        )

    @staticmethod
    def _score_to_payload(score: TopicScore | None) -> dict[str, Any] | None:
        if score is None:
            return None
        return {
            "candidate_id": str(score.candidate_id),
            "total": str(score.total),
            "evidence": [
                {
                    "evidence_type": evidence.evidence_type.value,
                    "value": str(evidence.value),
                    "sample_size": evidence.sample_size,
                    "confidence": str(evidence.confidence),
                }
                for evidence in score.evidence
            ],
            "rationale": list(score.rationale),
        }

    @staticmethod
    def _payload_to_score(payload: dict[str, Any]) -> TopicScore:
        evidence = tuple(
            TopicEvidence(
                evidence_type=TopicEvidenceType(item["evidence_type"]),
                value=Decimal(str(item["value"])),
                sample_size=int(item.get("sample_size", 0)),
                confidence=Decimal(str(item.get("confidence", "0"))),
            )
            for item in payload.get("evidence", [])
        )
        return TopicScore(
            candidate_id=UUID(str(payload["candidate_id"])),
            total=Decimal(str(payload["total"])),
            evidence=evidence,
            rationale=tuple(item for item in payload.get("rationale", []) if isinstance(item, str)),
        )

    @staticmethod
    def _parse_uuid_list(values: list[object]) -> tuple[UUID, ...]:
        try:
            return tuple(UUID(str(value)) for value in values)
        except (TypeError, ValueError) as exc:
            raise ValueError("topic decision candidate IDs must be valid UUIDs") from exc
