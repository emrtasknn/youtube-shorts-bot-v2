from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class CameraMotionType(StrEnum):
    STATIC = "static"
    PUSH_IN = "push_in"
    PULL_OUT = "pull_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    PAN_UP = "pan_up"
    PAN_DOWN = "pan_down"


@dataclass(frozen=True, slots=True)
class CameraMotionPlan:
    motion_type: CameraMotionType
    intensity: float = 0.0
    focus_x: float = 0.5
    focus_y: float = 0.5

    def __post_init__(self) -> None:
        if not 0.0 <= self.intensity <= 1.0:
            raise ValueError("Motion intensity must be between 0 and 1")
        if not 0.0 <= self.focus_x <= 1.0 or not 0.0 <= self.focus_y <= 1.0:
            raise ValueError("Motion focus must be between 0 and 1")

    @property
    def zoom_start(self) -> float:
        if self.motion_type is CameraMotionType.PULL_OUT:
            return 1.0 + self.intensity * 0.10
        return 1.0

    @property
    def zoom_end(self) -> float:
        if self.motion_type is CameraMotionType.PUSH_IN:
            return 1.0 + self.intensity * 0.10
        if self.motion_type is CameraMotionType.PULL_OUT:
            return 1.0
        return 1.0


class CameraMotionEngine:
    """Select bounded, deterministic motion without overriding visual semantics."""

    _PURPOSE_PREFERENCES = {
        "event": (CameraMotionType.PUSH_IN, CameraMotionType.PAN_RIGHT),
        "person": (CameraMotionType.PUSH_IN, CameraMotionType.PAN_LEFT),
        "place": (CameraMotionType.PAN_LEFT, CameraMotionType.PAN_RIGHT),
        "object": (CameraMotionType.PUSH_IN, CameraMotionType.PAN_UP),
        "comparison": (CameraMotionType.PAN_LEFT, CameraMotionType.PAN_RIGHT),
        "consequence": (CameraMotionType.PULL_OUT, CameraMotionType.PUSH_IN),
        "support_narration": (CameraMotionType.PUSH_IN, CameraMotionType.PAN_RIGHT),
    }

    def plan(
        self,
        *,
        purpose: str,
        duration_seconds: float,
        beat_index: int = 0,
        recent_motion: Sequence[CameraMotionType | str] = (),
    ) -> CameraMotionPlan:
        if duration_seconds <= 0:
            raise ValueError("Motion duration must be positive")
        if beat_index < 0:
            raise ValueError("Beat index must not be negative")

        if duration_seconds < 1.25:
            return CameraMotionPlan(CameraMotionType.STATIC)

        normalized_recent = {
            item.value if isinstance(item, CameraMotionType) else str(item)
            for item in recent_motion
        }
        options = self._PURPOSE_PREFERENCES.get(
            purpose.strip().lower(),
            (
                CameraMotionType.PUSH_IN,
                CameraMotionType.PAN_RIGHT,
                CameraMotionType.PULL_OUT,
            ),
        )
        ordered = tuple(
            options[(beat_index + offset) % len(options)]
            for offset in range(len(options))
        )
        selected = next(
            (motion for motion in ordered if motion.value not in normalized_recent),
            ordered[0],
        )

        # Keep short beats subtle and cap the maximum camera movement.
        intensity = min(1.0, max(0.35, duration_seconds / 6.0))
        focus_x = 0.5
        focus_y = 0.5
        if selected is CameraMotionType.PAN_LEFT:
            focus_x = 0.38
        elif selected is CameraMotionType.PAN_RIGHT:
            focus_x = 0.62
        elif selected is CameraMotionType.PAN_UP:
            focus_y = 0.38
        elif selected is CameraMotionType.PAN_DOWN:
            focus_y = 0.62

        return CameraMotionPlan(
            motion_type=selected,
            intensity=intensity,
            focus_x=focus_x,
            focus_y=focus_y,
        )
