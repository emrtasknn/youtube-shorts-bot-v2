from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from statistics import median

from app.application.services.retry_orchestrator import RetryAction


@dataclass(frozen=True, slots=True)
class RetryOutcomeObservation:
    """Historical evidence for one isolated retry intervention.

    An observation is causal only when exactly one targeted action was
    executed. Regeneration and escalation are intentionally excluded.
    """

    sequence: int
    action: RetryAction
    score_delta: float
    duration_seconds: float
    improved: bool


@dataclass(frozen=True, slots=True)
class RetryActionLearning:
    action: RetryAction
    sample_count: int
    success_rate: float
    average_gain: float
    median_duration_seconds: float
    confidence: float
    usable: bool


class RetryOutcomeLearning:
    """Learns conservative action-level retry outcomes from isolated evidence."""

    _LEARNABLE_ACTIONS = frozenset(
        {
            RetryAction.RESELECT_VISUALS,
            RetryAction.REPAIR_AUDIO,
            RetryAction.RECONCILE_TIMELINE,
        }
    )

    def __init__(
        self,
        *,
        minimum_samples: int = 2,
        recency_decay: float = 0.9,
        minimum_improvement: float = 1.0,
    ) -> None:
        if minimum_samples < 1:
            raise ValueError("minimum_samples must be positive")
        if not 0.0 < recency_decay <= 1.0:
            raise ValueError("recency_decay must be in (0, 1]")
        if minimum_improvement < 0:
            raise ValueError("minimum_improvement must be non-negative")
        self._minimum_samples = minimum_samples
        self._recency_decay = recency_decay
        self._minimum_improvement = minimum_improvement

    def learn(
        self,
        observations: tuple[RetryOutcomeObservation, ...],
    ) -> dict[RetryAction, RetryActionLearning]:
        latest = max((item.sequence for item in observations), default=0)
        learned: dict[RetryAction, RetryActionLearning] = {}

        for action in self._LEARNABLE_ACTIONS:
            items = [
                item
                for item in observations
                if item.action == action and item.duration_seconds >= 0
            ]
            if not items:
                continue

            weighted = [
                (item, self._weight(latest - item.sequence))
                for item in items
            ]
            weight_sum = sum(weight for _, weight in weighted)
            success_rate = (
                sum(weight for item, weight in weighted if item.improved) / weight_sum
                if weight_sum
                else 0.0
            )
            average_gain = (
                sum(weight * max(0.0, item.score_delta) for item, weight in weighted)
                / weight_sum
                if weight_sum
                else 0.0
            )
            durations = [item.duration_seconds for item in items if item.duration_seconds > 0]
            median_duration = median(durations) if durations else 0.0
            confidence = min(1.0, len(items) / self._minimum_samples)

            learned[action] = RetryActionLearning(
                action=action,
                sample_count=len(items),
                success_rate=round(success_rate, 4),
                average_gain=round(average_gain, 4),
                median_duration_seconds=round(median_duration, 4),
                confidence=round(confidence, 4),
                usable=len(items) >= self._minimum_samples,
            )

        return learned

    def expected_gain_multiplier(
        self,
        action: RetryAction,
        *,
        learned: dict[RetryAction, RetryActionLearning],
    ) -> float:
        evidence = learned.get(action)
        if evidence is None or not evidence.usable:
            return 1.0

        effectiveness = min(1.5, max(0.5, evidence.success_rate * 1.0 + evidence.average_gain / 40.0))
        multiplier = 1.0 + (effectiveness - 1.0) * evidence.confidence
        return round(min(1.5, max(0.5, multiplier)), 4)

    def _weight(self, age: int) -> float:
        return exp(age * log(self._recency_decay))

    @property
    def minimum_samples(self) -> int:
        return self._minimum_samples

    @property
    def minimum_improvement(self) -> float:
        return self._minimum_improvement
