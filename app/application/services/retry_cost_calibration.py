from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from app.application.services.retry_orchestrator import RetryAction


@dataclass(frozen=True, slots=True)
class RetryCostObservation:
    attempt: int
    actions: tuple[RetryAction, ...]
    duration_seconds: float


class RetryCostCalibration:
    """Calibrates retry action costs from measured execution duration.

    Duration is runtime telemetry, not provider billing. Bundle observations are
    therefore treated as shared evidence across the actions in an attempt.
    """

    def __init__(self, *, minimum_samples: int = 2, smoothing: float = 0.35) -> None:
        if minimum_samples < 1:
            raise ValueError("minimum_samples must be positive")
        if not 0.0 <= smoothing <= 1.0:
            raise ValueError("smoothing must be between 0 and 1")
        self._minimum_samples = minimum_samples
        self._smoothing = smoothing

    def calibrate(
        self,
        observations: tuple[RetryCostObservation, ...],
        *,
        base_costs: dict[RetryAction, float],
    ) -> dict[RetryAction, float]:
        if not observations:
            return dict(base_costs)

        durations = [item.duration_seconds for item in observations if item.duration_seconds > 0]
        if not durations:
            return dict(base_costs)

        baseline = median(durations)
        if baseline <= 0:
            return dict(base_costs)

        sample_count = len(durations)
        calibrated = dict(base_costs)
        if sample_count < self._minimum_samples:
            return calibrated

        for action in base_costs:
            action_durations = [
                item.duration_seconds
                for item in observations
                if action in item.actions and item.duration_seconds > 0
            ]
            if not action_durations:
                continue
            measured_ratio = median(action_durations) / baseline
            measured_cost = max(0.25, min(10.0, base_costs[action] * measured_ratio))
            calibrated[action] = round(
                base_costs[action] * (1.0 - self._smoothing)
                + measured_cost * self._smoothing,
                4,
            )
        return calibrated

    @property
    def minimum_samples(self) -> int:
        return self._minimum_samples
