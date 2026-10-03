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
