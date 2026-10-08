from pathlib import Path

import pytest

from app.application.services.camera_motion import (
    CameraMotionEngine,
    CameraMotionType,
    CameraMotionPlan,
)


def test_short_beats_use_static_fallback() -> None:
    plan = CameraMotionEngine().plan(
        purpose="event",
        duration_seconds=1.0,
    )
    assert plan.motion_type is CameraMotionType.STATIC
    assert plan.intensity == 0.0


def test_motion_is_deterministic_and_bounded() -> None:
    engine = CameraMotionEngine()
    first = engine.plan(purpose="event", duration_seconds=5.0, beat_index=0)
    second = engine.plan(purpose="event", duration_seconds=5.0, beat_index=0)

    assert first == second
    assert first.motion_type is CameraMotionType.PUSH_IN
    assert 0.35 <= first.intensity <= 1.0
    assert 1.0 <= first.zoom_end <= 1.10


def test_recent_motion_is_deprioritized() -> None:
    plan = CameraMotionEngine().plan(
        purpose="place",
        duration_seconds=5.0,
        recent_motion=(CameraMotionType.PAN_LEFT,),
    )
    assert plan.motion_type is CameraMotionType.PAN_RIGHT


def test_focus_remains_in_safe_normalized_bounds() -> None:
    for purpose in ("person", "place", "object", "comparison"):
        plan = CameraMotionEngine().plan(purpose=purpose, duration_seconds=4.0)
        assert 0.0 <= plan.focus_x <= 1.0
        assert 0.0 <= plan.focus_y <= 1.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"duration_seconds": 0},
        {"duration_seconds": -1},
        {"duration_seconds": 2, "beat_index": -1},
    ],
)
def test_invalid_motion_inputs_are_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        CameraMotionEngine().plan(purpose="event", **kwargs)


def test_invalid_motion_plan_is_rejected() -> None:
    with pytest.raises(ValueError):
        CameraMotionPlan(CameraMotionType.PUSH_IN, intensity=1.1)
