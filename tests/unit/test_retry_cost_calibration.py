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


def test_calibration_uses_relative_measured_duration() -> None:
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
                actions=(RetryAction.REGENERATE_VIDEO,),
                duration_seconds=3.0,
            ),
        ),
        base_costs={
            RetryAction.REPAIR_AUDIO: 1.5,
            RetryAction.REGENERATE_VIDEO: 2.5,
        },
    )

    assert result[RetryAction.REPAIR_AUDIO] == 0.75
    assert result[RetryAction.REGENERATE_VIDEO] == 3.75
