from app.application.ports.video_engine import VideoRenderRequest, VideoSceneInput
from app.infrastructure.video.ffmpeg import FFmpegCommandBuilder


def test_ffmpeg_command_contains_dynamic_ducking(tmp_path) -> None:
    scene = tmp_path / "scene.jpg"
    voice = tmp_path / "voice.mp3"
    background = tmp_path / "background.mp3"
    output = tmp_path / "output.mp4"
    scene.touch()
    voice.touch()
    background.touch()

    request = VideoRenderRequest(
        scenes=(VideoSceneInput(path=scene, duration_seconds=6, is_image=True),),
        output_path=output,
        voiceover_path=voice,
        background_audio_path=background,
    )

    command = FFmpegCommandBuilder().build(request)

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "[2:a]atrim=duration=6" in filter_complex
    assert "[voice]asplit=2[voice_mix][voice_sidechain];" in filter_complex
    assert "[bgm][voice_sidechain]sidechaincompress=" in filter_complex
    assert "[voice_mix][ducked]amix=inputs=2" in filter_complex
    assert "[aout]" in command


def test_ffmpeg_command_rejects_background_without_voiceover(tmp_path) -> None:
    scene = tmp_path / "scene.jpg"
    background = tmp_path / "background.mp3"
    output = tmp_path / "output.mp4"
    scene.touch()
    background.touch()

    request = VideoRenderRequest(
        scenes=(VideoSceneInput(path=scene, duration_seconds=6, is_image=True),),
        output_path=output,
        background_audio_path=background,
    )

    try:
        FFmpegCommandBuilder().build(request)
    except ValueError as exc:
        assert "voiceover" in str(exc)
    else:
        raise AssertionError("Expected background audio without voiceover to fail")
