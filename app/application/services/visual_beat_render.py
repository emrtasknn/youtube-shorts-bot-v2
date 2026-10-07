from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.application.ports.video_engine import VideoSceneInput
from app.application.services.visual_beat import VisualBeatTimeline


@dataclass(frozen=True, slots=True)
class VisualBeatRenderInput:
    """A beat asset paired with its semantic timeline position."""

    path: Path
    duration_seconds: float
    beat_index: int

    def to_video_scene_input(self) -> VideoSceneInput:
        return VideoSceneInput(
            path=self.path,
            duration_seconds=self.duration_seconds,
            is_image=self.path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"},
        )


def to_video_scene_inputs(
    timeline: VisualBeatTimeline,
    assets: tuple[Path, ...],
) -> tuple[VideoSceneInput, ...]:
    """Adapt beat assets to the existing renderer without changing its contract."""

    if len(assets) != len(timeline.beats):
        raise ValueError("Beat asset count must match visual beat count")

    return tuple(
        VisualBeatRenderInput(
            path=path,
            duration_seconds=beat.duration_seconds,
            beat_index=beat.beat_index,
        ).to_video_scene_input()
        for beat, path in zip(timeline.beats, assets, strict=True)
    )
