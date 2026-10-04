from pathlib import Path

import pytest

from app.application.ports.video_engine import VideoRenderRequest, VideoSceneInput
from app.infrastructure.video.ffmpeg import FFmpegVideoEngine


def make_request(tmp_path: Path) -> VideoRenderRequest:
    scenes = tuple(
        VideoSceneInput(
            path=tmp_path / f"scene-{index}.jpg",
            duration_seconds=6.0,
            is_image=True,
        )
        for index in range(3)
    )
    return VideoRenderRequest(
        scenes=scenes,
        output_path=tmp_path / "output.mp4",
    )


def test_render_timing_scales_all_scenes_to_voiceover_duration(tmp_path: Path) -> None:
    engine = FFmpegVideoEngine()
    request = make_request(tmp_path)

    durations = engine._resolve_scene_durations(request, 15.0)

    assert durations == pytest.approx((5.0, 5.0, 5.0))
    assert sum(durations) == pytest.approx(15.0)


def test_render_timing_preserves_planned_durations_without_voiceover(
    tmp_path: Path,
) -> None:
    engine = FFmpegVideoEngine()
    request = make_request(tmp_path)

    durations = engine._resolve_scene_durations(request, 0.0)

    assert durations == (6.0, 6.0, 6.0)
