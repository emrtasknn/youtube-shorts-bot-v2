from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.application.ports.video_engine import VideoSceneInput
from app.application.services.camera_motion import CameraMotionPlan
from app.application.services.visual_beat import VisualBeatTimeline


@dataclass(frozen=True, slots=True)
class VisualBeatRenderInput:
    """A beat asset paired with its semantic timeline position."""

    path: Path
    duration_seconds: float
    beat_index: int
    scene_index: int = 0
    visual_timeline: VisualBeatTimeline | None = None

    def to_video_scene_input(
        self,
        motion: CameraMotionPlan | None = None,
    ) -> VideoSceneInput:
        return VideoSceneInput(
            path=self.path,
            duration_seconds=self.duration_seconds,
            is_image=self.path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"},
            motion=motion,
            scene_index=self.scene_index,
            beat_index=self.beat_index,
            visual_timeline=self.visual_timeline,
        )


def to_video_scene_inputs(
    timeline: VisualBeatTimeline,
    assets: tuple[Path, ...],
    motions: tuple[CameraMotionPlan, ...] | None = None,
) -> tuple[VideoSceneInput, ...]:
    """Adapt beat assets to the existing renderer without changing its contract."""

    if len(assets) != len(timeline.beats):
        raise ValueError("Beat asset count must match visual beat count")
    if motions is not None and len(motions) != len(timeline.beats):
        raise ValueError("Motion plan count must match visual beat count")

    return tuple(
        VideoSceneInput(
            path=path,
            duration_seconds=beat.duration_seconds,
            is_image=path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"},
            motion=None if motions is None else motions[index],
            scene_index=timeline.scene_index,
            beat_index=beat.beat_index,
            visual_timeline=timeline,
        )
        for index, (beat, path) in enumerate(zip(timeline.beats, assets, strict=True))
    )
