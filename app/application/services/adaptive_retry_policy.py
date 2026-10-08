from __future__ import annotations

from dataclasses import dataclass

from app.application.services.retry_orchestrator import RetryAction, RetryPlan
from app.application.services.video_judge import VideoJudgeReport


@dataclass(frozen=True, slots=True)
class RetryEffectivenessObservation:
    attempt: int
    actions: tuple[RetryAction, ...]
    before_score: float
    after_score: float
    score_delta: float
    improved: bool
    dimension_deltas: dict[str, float]


@dataclass(frozen=True, slots=True)
class AdaptiveRetryDecision:
    actions: tuple[RetryAction, ...]
    excluded_actions: tuple[RetryAction, ...]
    reason: str


class AdaptiveRetryPolicy:
    """Chooses retry actions using measured quality improvement.

    An action that failed to improve the judge score is not repeated on a
    subsequent attempt. The policy is conservative: semantic regeneration
    remains available when targeted actions are exhausted.
    """

    def __init__(self, *, minimum_score_improvement: float = 1.0) -> None:
        if minimum_score_improvement < 0:
            raise ValueError("minimum_score_improvement must be non-negative")
        self._minimum_score_improvement = minimum_score_improvement

    def observe(
        self,
        *,
        previous: VideoJudgeReport,
        current: VideoJudgeReport,
        actions: tuple[RetryAction, ...],
        attempt: int,
    ) -> RetryEffectivenessObservation:
        deltas = {
            key: round(
                current.dimension_scores.get(key, 0.0)
                - previous.dimension_scores.get(key, 0.0),
                2,
            )
            for key in set(previous.dimension_scores) | set(current.dimension_scores)
        }
        delta = round(current.score - previous.score, 2)
        return RetryEffectivenessObservation(
            attempt=attempt,
            actions=actions,
            before_score=previous.score,
            after_score=current.score,
            score_delta=delta,
            improved=delta >= self._minimum_score_improvement,
            dimension_deltas=deltas,
        )

    def adapt(
        self,
        plan: RetryPlan,
        *,
        observations: tuple[RetryEffectivenessObservation, ...],
    ) -> AdaptiveRetryDecision:
        if not observations:
            return AdaptiveRetryDecision(
                actions=plan.actions,
                excluded_actions=(),
                reason="no_prior_retry_observation",
            )

        failed_actions = {
            action
            for observation in observations
            if not observation.improved
            for action in observation.actions
            if action not in {
                RetryAction.REGENERATE_VIDEO,
                RetryAction.ESCALATE,
            }
        }
        actions = tuple(action for action in plan.actions if action not in failed_actions)
        excluded = tuple(action for action in plan.actions if action in failed_actions)

        if not actions or all(
            action in {RetryAction.REGENERATE_VIDEO, RetryAction.ESCALATE}
            for action in actions
        ):
            actions = (RetryAction.REGENERATE_VIDEO,)
            reason = "targeted_actions_failed_use_general_regeneration"
        else:
            reason = "excluded_non_improving_actions"

        return AdaptiveRetryDecision(
            actions=actions,
            excluded_actions=excluded,
            reason=reason,
        )

    @property
    def minimum_score_improvement(self) -> float:
        return self._minimum_score_improvement
