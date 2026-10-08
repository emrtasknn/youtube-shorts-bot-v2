from app.application.services.retry_cost_calibration import (
    RetryCostCalibration,
    RetryCostObservation,
)
from app.application.services.retry_orchestrator import RetryAction


def test_calibration_preserves_base_cost_without_enough_samples() -> None:
    calibration = RetryCostCalibration(minimum_samples=2)
    result = calibration.calibrate(
        (
            RetryCostObservation(
                attempt=2,
                actions=(RetryAction.REPAIR_AUDIO,),
                duration_seconds=2.0,
            ),
        ),
        base_costs={RetryAction.REPAIR_AUDIO: 1.5},
    )

    assert result[RetryAction.REPAIR_AUDIO] == 1.5


def test_calibration_uses_measured_duration_after_minimum_samples() -> None:
    calibration = RetryCostCalibration(minimum_samples=2, smoothing=1.0)
    result = calibration.calibrate(
        (
            RetryCostObservation(
                attempt=2,
                actions=(RetryAction.REPAIR_AUDIO,),
                duration_seconds=1.0,
            ),
            RetryCostObservation(
                attempt=3,
                actions=(RetryAction.REPAIR_AUDIO,),
                duration_seconds=3.0,
            ),
        ),
        base_costs={RetryAction.REPAIR_AUDIO: 1.5},
    )

    assert result[RetryAction.REPAIR_AUDIO] == 1.5
