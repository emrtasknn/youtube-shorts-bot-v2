from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from app.domain.topic_optimization import (
    TopicCandidate,
    TopicDecisionStatus,
    TopicEvidenceType,
    TopicScore,
    TopicSelectionDecision,
)


@dataclass(frozen=True, slots=True)
class TopicSelectionPolicy:
    """Fixed, bounded policy for deterministic topic selection."""

    minimum_score: Decimal = Decimal("0.60")

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_score <= 1:
            raise ValueError("minimum topic score must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class TopicSelectionService:
    """Select one scored candidate without mutating production behavior."""

    policy: TopicSelectionPolicy = TopicSelectionPolicy()

    def select(
        self,
        candidates: tuple[TopicCandidate, ...],
        scores: tuple[TopicScore, ...],
    ) -> TopicSelectionDecision:
        candidate_ids = tuple(sorted((candidate.candidate_id for candidate in candidates), key=str))
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate IDs must be unique")

        score_by_id: dict[UUID, TopicScore] = {}
        for score in scores:
            if score.candidate_id in score_by_id:
                raise ValueError("topic scores must contain unique candidate IDs")
            if score.candidate_id in candidate_ids:
                score_by_id[score.candidate_id] = score

        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        eligible = [
            score for score in score_by_id.values() if score.total >= self.policy.minimum_score
        ]
        decision_id = self._decision_id(candidate_ids, tuple(score_by_id.values()))

        if not eligible:
            return TopicSelectionDecision.no_selection(
                candidate_ids=candidate_ids,
                rationale=(
                    f"No candidate reached the minimum score of {self.policy.minimum_score}.",
                ),
                decision_id=decision_id,
            )

        winner = max(
            eligible,
            key=lambda score: (
                score.total,
                self._novelty_value(score),
                -self._uuid_rank(score.candidate_id),
            ),
        )
        candidate = candidate_by_id[winner.candidate_id]

        return TopicSelectionDecision(
            decision_id=decision_id,
            status=TopicDecisionStatus.SELECTED,
            selected_candidate_id=candidate.candidate_id,
            selected_topic=candidate.title,
            candidate_ids=candidate_ids,
            selected_score=winner,
            rationale=(
                f"Selected highest-scoring eligible candidate at {winner.total}.",
                f"Minimum selection score is {self.policy.minimum_score}.",
            ),
        )

    def _decision_id(
        self,
        candidate_ids: tuple[UUID, ...],
        scores: tuple[TopicScore, ...],
    ) -> UUID:
        payload = {
            "policy_minimum_score": str(self.policy.minimum_score),
            "candidate_ids": [str(item) for item in candidate_ids],
            "scores": [
                {
                    "candidate_id": str(score.candidate_id),
                    "total": str(score.total),
                    "evidence": [
                        {
                            "type": evidence.evidence_type.value,
                            "value": str(evidence.value),
                            "sample_size": evidence.sample_size,
                            "confidence": str(evidence.confidence),
                        }
                        for evidence in score.evidence
                    ],
                    "rationale": list(score.rationale),
                }
                for score in sorted(scores, key=lambda item: str(item.candidate_id))
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return uuid5(NAMESPACE_URL, f"m11-topic-selection-v1:{canonical}")

    @staticmethod
    def _novelty_value(score: TopicScore) -> Decimal:
        for evidence in score.evidence:
            if evidence.evidence_type is TopicEvidenceType.NOVELTY:
                return evidence.value
        return Decimal("0")

    @staticmethod
    def _uuid_rank(candidate_id: UUID) -> int:
        return candidate_id.int
