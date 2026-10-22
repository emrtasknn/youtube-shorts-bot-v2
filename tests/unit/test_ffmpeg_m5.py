from __future__ import annotations

from pathlib import Path

from app.application.ports.video_engine import VideoRenderRequest, VideoSceneInput
from app.infrastructure.video.ffmpeg import FFmpegCommandBuilder


def test_ffmpeg_builder_maps_voiceover_and_subtitles(tmp_path: Path) -> None:
    scene = tmp_path / "scene.jpg"
    audio = tmp_path / "voice.mp3"
    subtitles = tmp_path / "captions.ass"
    output = tmp_path / "out.mp4"
    for path in (scene, audio, subtitles):
        path.write_bytes(b"data")

    request = VideoRenderRequest(
        scenes=(VideoSceneInput(path=scene, duration_seconds=5, is_image=True),),
        output_path=output,
        voiceover_path=audio,
    )
    command = FFmpegCommandBuilder().build(
        request,
        scene_durations=(8.5,),
        subtitle_path=subtitles,
    )

    assert command.index("-i") < command.index("-filter_complex")
    assert str(audio) in command
    command_text = " ".join(command)
    assert str(subtitles) in command_text
    assert "subtitles=" in command_text
    assert "trim=duration=8.5" in " ".join(command)
    assert "-shortest" in command


def test_ffmpeg_builder_uses_generic_stream_loop_for_still_images(tmp_path: Path) -> None:
    scene = tmp_path / "scene.jpg"
    scene.write_bytes(b"image-data")
    request = VideoRenderRequest(
        scenes=(VideoSceneInput(path=scene, duration_seconds=3, is_image=True),),
        output_path=tmp_path / "out.mp4",
    )

    command = FFmpegCommandBuilder().build(request)

    image_input = command.index(str(scene))
    assert command[image_input - 3 : image_input] == ["-stream_loop", "-1", "-t"]
    assert "-loop" not in command
