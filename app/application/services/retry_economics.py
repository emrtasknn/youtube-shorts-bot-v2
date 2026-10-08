from __future__ import annotations

from dataclasses import dataclass

from app.application.services.adaptive_retry_policy import RetryEffectivenessObservation
from app.application.services.retry_cost_calibration import RetryCostCalibration, RetryCostObservation
from app.application.services.retry_orchestrator import RetryAction, RetryPlan
from app.application.services.retry_outcome_learning import RetryOutcomeLearning, RetryOutcomeObservation
from app.application.services.video_judge import VideoJudgeReport


@dataclass(frozen=True, slots=True)
class RetryActionEconomics:
    action: RetryAction
    estimated_cost: float
    expected_gain: float
    efficiency: float


@dataclass(frozen=True, slots=True)
class RetryEconomicsDecision:
    actions: tuple[RetryAction, ...]
    rankings: tuple[RetryActionEconomics, ...]
    preserved_actions: tuple[RetryAction, ...]
    reason: str


class RetryEconomicsPolicy:
    """Ranks retry interventions by expected quality gain per measured cost."""

    _BASE_COSTS = {
        RetryAction.RESELECT_VISUALS: 4.0,
        RetryAction.REPAIR_AUDIO: 1.5,
        RetryAction.RECONCILE_TIMELINE: 1.0,
        RetryAction.REGENERATE_VIDEO: 2.5,
        RetryAction.ESCALATE: 100.0,
    }
    _DIMENSION_MAP = {
        RetryAction.RESELECT_VISUALS: "visual",
        RetryAction.REPAIR_AUDIO: "audio",
        RetryAction.RECONCILE_TIMELINE: "synchronization",
    }

    def __init__(self, *, cost_calibration: RetryCostCalibration | None = None) -> None:
        self._cost_calibration = cost_calibration or RetryCostCalibration()
        self._outcome_learning = RetryOutcomeLearning()

    def rank(
        self,
        plan: RetryPlan,
        *,
        report: VideoJudgeReport,
        observations: tuple[RetryEffectivenessObservation, ...] = (),
        historical_observations: tuple[RetryEffectivenessObservation, ...] = (),
    ) -> RetryEconomicsDecision:
        if not plan.actions:
            return RetryEconomicsDecision((), (), (), "no_retry_actions")

        costs = self._calibrated_costs(observations)
        learned = self._learned_outcomes(historical_observations)
        scored: list[RetryActionEconomics] = []
        for action in plan.actions:
            cost = costs[action]
            gain = self._expected_gain(action, plan, report, observations)
            gain *= self._outcome_learning.expected_gain_multiplier(action, learned=learned)
            efficiency = round(gain / cost, 4) if cost else gain
            scored.append(
                RetryActionEconomics(
                    action=action,
                    estimated_cost=round(cost, 4),
                    expected_gain=round(gain, 2),
                    efficiency=efficiency,
                )
            )

        ranked = tuple(sorted(scored, key=lambda item: (-item.efficiency, item.estimated_cost)))
        actions = tuple(item.action for item in ranked)
        preserved = tuple(
            action
            for action in (
                RetryAction.RESELECT_VISUALS,
                RetryAction.REPAIR_AUDIO,
                RetryAction.RECONCILE_TIMELINE,
            )
            if action not in actions
        )
        measured = any(observation.duration_seconds > 0 for observation in observations)
        learned_signal = any(evidence.usable for evidence in learned.values())
        if learned_signal and measured:
            reason = "ranked_by_measured_gain_per_cost_with_historical_learning"
        elif learned_signal:
            reason = "ranked_by_historical_learning_and_expected_gain_per_cost"
        elif measured:
            reason = "ranked_by_measured_gain_per_cost"
        else:
            reason = "ranked_by_expected_gain_per_cost"
        return RetryEconomicsDecision(
            actions=actions,
            rankings=ranked,
            preserved_actions=preserved,
            reason=reason,
        )

    def _learned_outcomes(
        self,
        observations: tuple[RetryEffectivenessObservation, ...],
    ) -> dict[RetryAction, object]:
        isolated = tuple(
            RetryOutcomeObservation(
                sequence=index,
                action=observation.actions[0],
                score_delta=observation.score_delta,
                duration_seconds=max(0.0, observation.duration_seconds),
                improved=observation.improved,
            )
            for index, observation in enumerate(observations, start=1)
            if len(observation.actions) == 1
            and observation.actions[0]
            in {
                RetryAction.RESELECT_VISUALS,
                RetryAction.REPAIR_AUDIO,
                RetryAction.RECONCILE_TIMELINE,
            }
        )
        return self._outcome_learning.learn(isolated)

    def _calibrated_costs(
        self,
        observations: tuple[RetryEffectivenessObservation, ...],
    ) -> dict[RetryAction, float]:
        telemetry = tuple(
            RetryCostObservation(
                attempt=observation.attempt,
                actions=observation.actions,
                duration_seconds=observation.duration_seconds,
            )
            for observation in observations
            if observation.duration_seconds > 0
        )
        return self._cost_calibration.calibrate(
            telemetry,
            base_costs=self._BASE_COSTS,
        )

    def _expected_gain(
        self,
        action: RetryAction,
        plan: RetryPlan,
        report: VideoJudgeReport,
        observations: tuple[RetryEffectivenessObservation, ...],
    ) -> float:
        if action == RetryAction.ESCALATE:
            return 0.0

        dimension = self._DIMENSION_MAP.get(action)
        deficit = (
            max(0.0, 100.0 - report.dimension_scores.get(dimension, 100.0)) if dimension else 0.0
        )
        alignment = 8.0 if self._reason_maps_to_action(plan.reasons, action) else 2.0
        historical = [
            observation.score_delta
            for observation in observations
            if action in observation.actions and observation.improved
        ]
        history_gain = sum(historical) / len(historical) if historical else 0.0
        return max(1.0, min(40.0, deficit * 0.25 + alignment + max(0.0, history_gain)))

    @staticmethod
    def _reason_maps_to_action(
        reasons: tuple[str, ...],
        action: RetryAction,
    ) -> bool:
        mapping = {
            "excessive_visual_fallbacks": RetryAction.RESELECT_VISUALS,
            "audio_qc_failed": RetryAction.REPAIR_AUDIO,
            "synchronization_failed": RetryAction.RECONCILE_TIMELINE,
        }
        return any(mapping.get(reason) == action for reason in reasons)

    @property
    def base_costs(self) -> dict[RetryAction, float]:
        return dict(self._BASE_COSTS)
