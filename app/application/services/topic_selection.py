from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

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
        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        score_by_id = {
            score.candidate_id: score
            for score in scores
            if score.candidate_id in candidate_by_id
        }
        eligible = [
            score
            for score in score_by_id.values()
            if score.total >= self.policy.minimum_score
        ]

        candidate_ids = tuple(sorted(candidate_by_id, key=str))
        if not eligible:
            return TopicSelectionDecision.no_selection(
                candidate_ids=candidate_ids,
                rationale=(
                    f"No candidate reached the minimum score of "
                    f"{self.policy.minimum_score}.",
                ),
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
            decision_id=uuid4(),
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

    @staticmethod
    def _novelty_value(score: TopicScore) -> Decimal:
        for evidence in score.evidence:
            if evidence.evidence_type is TopicEvidenceType.NOVELTY:
                return evidence.value
        return Decimal("0")

    @staticmethod
    def _uuid_rank(candidate_id: UUID) -> int:
        return candidate_id.int
