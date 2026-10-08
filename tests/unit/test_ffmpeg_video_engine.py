from pathlib import Path

import pytest

from app.application.ports.video_engine import VideoRenderRequest, VideoSceneInput
from app.application.services.camera_motion import CameraMotionPlan, CameraMotionType
from app.infrastructure.video.ffmpeg import FFmpegCommandBuilder, FFmpegVideoEngine


def test_builder_creates_vertical_scene_pipeline(tmp_path: Path) -> None:
    image = tmp_path / "scene.jpg"
    image.touch()
    output = tmp_path / "output.mp4"
    request = VideoRenderRequest(
        scenes=(VideoSceneInput(image, 2.5, is_image=True),),
        output_path=output,
    )

    command = FFmpegCommandBuilder().build(request)
    filter_complex = command[command.index("-filter_complex") + 1]

    assert command[:4] == ["ffmpeg", "-y", "-hide_banner", "-loglevel"]
    assert "-loop" in command
    assert "scale=1080:1920" in filter_complex
    assert "crop=1080:1920" in filter_complex
    assert "concat=n=1:v=1:a=0" in filter_complex
    assert command[-2:] == ["mp4", str(output)]


def test_builder_supports_mixed_scenes_and_voiceover(tmp_path: Path) -> None:
    image = tmp_path / "scene.jpg"
    video = tmp_path / "scene.mp4"
    voiceover = tmp_path / "voice.mp3"
    output = tmp_path / "output.mp4"
    for path in (image, video, voiceover):
        path.touch()

    request = VideoRenderRequest(
        scenes=(VideoSceneInput(image, 2.0, is_image=True), VideoSceneInput(video, 3.0)),
        output_path=output,
        voiceover_path=voiceover,
    )
    command = FFmpegCommandBuilder().build(request)
    filter_complex_index = command.index("-filter_complex")
    voiceover_index = command.index(str(voiceover))
    filter_complex = command[filter_complex_index + 1]

    assert command.count("-i") == 3
    assert voiceover_index < filter_complex_index
    assert command.index("-map") > filter_complex_index
    assert "[0:v]" in filter_complex
    assert "[1:v]" in filter_complex
    assert "concat=n=2:v=1:a=0" in filter_complex
    assert "2:a:0" in command
    assert "-shortest" in command


def test_builder_renders_visual_beats_in_order_with_exact_planned_durations(
    tmp_path: Path,
) -> None:
    beats = tuple(tmp_path / f"beat-{index}.jpg" for index in range(3))
    for path in beats:
        path.touch()
    output = tmp_path / "output.mp4"

    request = VideoRenderRequest(
        scenes=tuple(
            VideoSceneInput(path, duration, is_image=True)
            for path, duration in zip(beats, (1.2, 2.3, 1.5), strict=True)
        ),
        output_path=output,
    )

    command = FFmpegCommandBuilder().build(request)
    filter_complex = command[command.index("-filter_complex") + 1]

    assert [str(path) for path in beats] == [command[command.index(str(path))] for path in beats]
    assert "trim=duration=1.2" in filter_complex
    assert "trim=duration=2.3" in filter_complex
    assert "trim=duration=1.5" in filter_complex
    assert "concat=n=3:v=1:a=0" in filter_complex


def test_engine_scales_beat_durations_to_target_duration():
    engine = FFmpegVideoEngine()
    request = VideoRenderRequest(
        scenes=(
            VideoSceneInput(Path("beat0.jpg"), 1.0, is_image=True),
            VideoSceneInput(Path("beat1.jpg"), 2.0, is_image=True),
            VideoSceneInput(Path("beat2.jpg"), 3.0, is_image=True),
        ),
        output_path=Path("output.mp4"),
    )

    durations = engine._resolve_scene_durations(request, 12.0)

    assert durations == pytest.approx((2.0, 4.0, 6.0))
    assert sum(durations) == pytest.approx(12.0)


def test_builder_rejects_empty_scenes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="At least one video scene"):
        FFmpegCommandBuilder().build(
            VideoRenderRequest(scenes=(), output_path=tmp_path / "output.mp4")
        )


def test_builder_rejects_missing_scene_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jpg"
    with pytest.raises(FileNotFoundError):
        FFmpegCommandBuilder().build(
            VideoRenderRequest(
                scenes=(VideoSceneInput(missing, 1.0, is_image=True),),
                output_path=tmp_path / "output.mp4",
            )
        )


def test_builder_passes_paths_as_arguments(tmp_path: Path) -> None:
    image = tmp_path / "scene;touch-HACKED.jpg"
    image.touch()
    output = tmp_path / "output.mp4"
    command = FFmpegCommandBuilder().build(
        VideoRenderRequest(
            scenes=(VideoSceneInput(image, 1.0, is_image=True),),
            output_path=output,
        )
    )

    assert str(image) in command
    assert "touch-HACKED.jpg" not in command[:-1]


def test_builder_integrates_subtitle_file_filter(tmp_path: Path) -> None:
    image = tmp_path / "scene.jpg"
    subtitle = tmp_path / "captions.ass"
    output = tmp_path / "output.mp4"
    image.touch()
    subtitle.write_text("[Script Info]\\n", encoding="utf-8")

    request = VideoRenderRequest(
        scenes=(VideoSceneInput(image, 2.0, is_image=True),),
        output_path=output,
        subtitle_text="hello world",
    )

    command = FFmpegCommandBuilder().build(request, subtitle_path=subtitle)
    filter_complex = command[command.index("-filter_complex") + 1]

    assert str(subtitle) in filter_complex
    assert "subtitles=" in filter_complex
    assert "[vsub]" in filter_complex


def test_builder_adds_bounded_zoompan_for_image_motion(tmp_path: Path) -> None:
    image = tmp_path / "scene.jpg"
    image.touch()
    output = tmp_path / "output.mp4"
    request = VideoRenderRequest(
        scenes=(
            VideoSceneInput(
                image,
                4.0,
                is_image=True,
                motion=CameraMotionPlan(
                    CameraMotionType.PUSH_IN,
                    intensity=0.8,
                    focus_x=0.5,
                    focus_y=0.5,
                ),
            ),
        ),
        output_path=output,
        fps=30,
    )

    command = FFmpegCommandBuilder().build(request)
    filter_complex = command[command.index("-filter_complex") + 1]

    assert "zoompan=" in filter_complex
    assert "d=1" in filter_complex
    assert "s=1080x1920" in filter_complex
    assert "fps=30" in filter_complex


def test_builder_keeps_static_image_without_motion_filter(tmp_path: Path) -> None:
    image = tmp_path / "scene.jpg"
    image.touch()
    output = tmp_path / "output.mp4"
    request = VideoRenderRequest(
        scenes=(VideoSceneInput(image, 2.0, is_image=True),),
        output_path=output,
    )

    command = FFmpegCommandBuilder().build(request)
    filter_complex = command[command.index("-filter_complex") + 1]

    assert "zoompan=" not in filter_complex


def test_builder_rejects_invalid_motion_contract(tmp_path: Path) -> None:
    image = tmp_path / "scene.jpg"
    image.touch()
    output = tmp_path / "output.mp4"
    request = VideoRenderRequest(
        scenes=(VideoSceneInput(image, 2.0, is_image=True, motion=object()),),
        output_path=output,
    )

    with pytest.raises(TypeError, match="CameraMotionPlan"):
        FFmpegCommandBuilder().build(request)
