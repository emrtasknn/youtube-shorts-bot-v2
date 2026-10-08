from pathlib import Path

import pytest

from app.application.services.camera_motion import CameraMotionPlan, CameraMotionType
from app.application.services.scene_contract import build_scene_contract
from app.application.services.visual_beat import VisualBeatCompiler
from app.application.services.visual_beat_render import to_video_scene_inputs


def _timeline():
    scene = build_scene_contract(
        {
            "narration": "Rome expanded across the Mediterranean. Its armies secured key ports.",
            "visual_goal": "Show Roman expansion",
            "visual_query": "Roman Empire Mediterranean expansion",
            "purpose": "event",
            "subject": "Roman Empire",
            "action": "expanding",
            "entities": ["Rome", "Roman Empire"],
            "location": "Mediterranean",
            "era": "ancient Rome",
            "visual_intent": "territorial expansion",
            "visual_style": "documentary",
            "must_show": ["Roman territory"],
            "must_avoid": ["modern borders"],
        }
    )
    return VisualBeatCompiler().compile(
        scene,
        scene_index=0,
        scene_duration_seconds=6.0,
    )


def test_visual_beats_adapt_to_existing_video_scene_inputs() -> None:
    timeline = _timeline()
    assets = tuple(Path(f"/tmp/beat-{index}.jpg") for index in range(len(timeline.beats)))

    inputs = to_video_scene_inputs(timeline, assets)

    assert len(inputs) == len(timeline.beats)
    assert tuple(item.duration_seconds for item in inputs) == tuple(
        beat.duration_seconds for beat in timeline.beats
    )
    assert all(item.is_image for item in inputs)


def test_visual_beat_render_adapter_requires_one_asset_per_beat() -> None:
    timeline = _timeline()

    with pytest.raises(ValueError, match="Beat asset count must match"):
        to_video_scene_inputs(timeline, (Path("/tmp/only-one.jpg"),))


def test_visual_beat_render_adapter_attaches_motion_plans() -> None:
    timeline = _timeline()
    assets = tuple(Path(f"/tmp/beat-{index}.jpg") for index in range(len(timeline.beats)))
    motions = tuple(
        CameraMotionPlan(CameraMotionType.PUSH_IN, intensity=0.5) for _ in timeline.beats
    )

    inputs = to_video_scene_inputs(timeline, assets, motions)

    assert tuple(item.motion for item in inputs) == motions


def test_visual_beat_render_adapter_requires_one_motion_per_beat() -> None:
    timeline = _timeline()
    assets = tuple(Path(f"/tmp/beat-{index}.jpg") for index in range(len(timeline.beats)))

    with pytest.raises(ValueError, match="Motion plan count must match"):
        to_video_scene_inputs(
            timeline,
            assets,
            (CameraMotionPlan(CameraMotionType.PUSH_IN, intensity=0.5),),
        )
