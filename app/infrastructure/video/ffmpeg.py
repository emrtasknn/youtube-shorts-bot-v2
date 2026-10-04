from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TypedDict

from app.application.ports.video_engine import (
    VideoRenderRequest,
    VideoRenderResult,
)
from app.application.services.audio_ducking import AudioDucking, DuckingConfig
from app.application.services.scene_timing import SceneTimingAllocator
from app.application.services.subtitles import write_ass


class MediaProbe(TypedDict):
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


class FFmpegCommandBuilder:
    def __init__(self, executable: str = "ffmpeg") -> None:
        self._executable = executable

    def build(
        self,
        request: VideoRenderRequest,
        *,
        scene_durations: tuple[float, ...] | None = None,
        subtitle_path: Path | None = None,
    ) -> list[str]:
        if not request.scenes:
            raise ValueError("At least one video scene is required")
        if request.width <= 0 or request.height <= 0:
            raise ValueError("Video dimensions must be positive")
        if request.fps <= 0:
            raise ValueError("Video FPS must be positive")
        durations = scene_durations or tuple(scene.duration_seconds for scene in request.scenes)
        if len(durations) != len(request.scenes):
            raise ValueError("Scene duration count must match scene count")

        for scene, duration in zip(request.scenes, durations, strict=True):
            if duration <= 0:
                raise ValueError("Scene duration must be positive")
            if not scene.path.is_file():
                raise FileNotFoundError(scene.path)

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [self._executable, "-y", "-hide_banner", "-loglevel", "error"]
        filter_inputs: list[str] = []

        for index, (scene, duration) in enumerate(zip(request.scenes, durations, strict=True)):
            if scene.is_image:
                command.extend(["-loop", "1", "-t", str(duration)])
            command.extend(["-i", str(scene.path)])
            filter_inputs.append(
                f"[{index}:v]scale={request.width}:{request.height}:"
                f"force_original_aspect_ratio=increase,"
                f"crop={request.width}:{request.height},setsar=1,fps={request.fps},"
                f"trim=duration={duration},setpts=PTS-STARTPTS[v{index}]"
            )

        audio_input_index: int | None = None
        background_audio_index: int | None = None
        if request.background_audio_path is not None and request.voiceover_path is None:
            raise ValueError("Background audio requires a voiceover for ducking")
        if request.voiceover_path is not None:
            if not request.voiceover_path.is_file():
                raise FileNotFoundError(request.voiceover_path)
            audio_input_index = len(request.scenes)
            command.extend(["-i", str(request.voiceover_path)])

        if request.background_audio_path is not None:
            if not request.background_audio_path.is_file():
                raise FileNotFoundError(request.background_audio_path)
            background_audio_index = len(request.scenes) + 1
            command.extend(["-stream_loop", "-1", "-i", str(request.background_audio_path)])

        concat_inputs = "".join(f"[v{index}]" for index in range(len(request.scenes)))
        filter_complex = ";".join(filter_inputs)
        filter_complex += (
            f";{concat_inputs}concat=n={len(request.scenes)}:v=1:a=0,format=yuv420p[vout]"
        )
        video_map = "[vout]"
        if subtitle_path is not None:
            if not subtitle_path.is_file():
                raise FileNotFoundError(subtitle_path)
            escaped = str(subtitle_path).replace("\\", "\\\\").replace(":", "\\:")
            filter_complex += (
                f";[vout]subtitles='{escaped}':"
                "force_style='FontName=Arial,FontSize=62,Bold=1,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                "BackColour=&H99000000,Outline=4,Shadow=1,"
                "Alignment=2,MarginL=80,MarginR=80,MarginV=390'[vsub]"
            )
            video_map = "[vsub]"
        command.extend(["-filter_complex", filter_complex, "-map", video_map])

        if audio_input_index is not None:
            if background_audio_index is not None:
                ducking = AudioDucking(
                    DuckingConfig(
                        background_volume=request.background_volume,
                        threshold=request.ducking_threshold,
                        ratio=request.ducking_ratio,
                        attack_ms=request.ducking_attack_ms,
                        release_ms=request.ducking_release_ms,
                    )
                )
                filter_complex += (
                    f";[{audio_input_index}:a]aformat=sample_fmts=fltp[voice];"
                    f"[{background_audio_index}:a]atrim=duration={sum(durations):g},"
                    "asetpts=PTS-STARTPTS[background];"
                    + ducking.build_filter(
                        voice_label="voice",
                        background_label="background",
                        output_label="aout",
                    )
                )
                command[command.index("-filter_complex") + 1] = filter_complex
                command.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-shortest"])
            else:
                command.extend(
                    [
                        "-map",
                        f"{audio_input_index}:a:0",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        "-shortest",
                    ]
                )

        command.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-movflags",
                "+faststart",
                "-r",
                str(request.fps),
                "-f",
                "mp4",
                str(request.output_path),
            ]
        )
        return command


class FFmpegVideoEngine:
    def __init__(
        self,
        executable: str = "ffmpeg",
        *,
        ffprobe_executable: str = "ffprobe",
        timeout_seconds: float = 300.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("FFmpeg timeout must be positive")
        self._builder = FFmpegCommandBuilder(executable)
        self._ffprobe = ffprobe_executable
        self._timeout_seconds = timeout_seconds

    async def render(self, request: VideoRenderRequest) -> VideoRenderResult:
        audio_duration = 0.0
        if request.voiceover_path is not None:
            audio_duration = await self._probe_duration(request.voiceover_path)

        scene_durations = tuple(scene.duration_seconds for scene in request.scenes)
        if audio_duration:
            scene_durations = SceneTimingAllocator().allocate(
                scene_durations,
                audio_duration,
            )

        subtitle_path: Path | None = None
        if request.subtitle_text:
            subtitle_duration = audio_duration or sum(scene_durations)
            subtitle_path = request.output_path.with_suffix(".ass")
            write_ass(subtitle_path, request.subtitle_text, subtitle_duration)

        command = self._builder.build(
            request,
            scene_durations=scene_durations,
            subtitle_path=subtitle_path,
        )
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=self._timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError("FFmpeg render timed out") from exc

        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"FFmpeg render failed with exit code {process.returncode}: {message}"
            )
        if not request.output_path.is_file():
            raise RuntimeError("FFmpeg completed without producing the output file")

        metadata = await self._probe_media(request.output_path)
        if metadata["width"] != request.width or metadata["height"] != request.height:
            raise RuntimeError("Rendered video dimensions do not match the requested 9:16 output")
        if metadata["fps"] <= 0:
            raise RuntimeError("Rendered video has an invalid frame rate")
        if request.voiceover_path is not None and not metadata["has_audio"]:
            raise RuntimeError("Rendered video is missing its audio stream")

        return VideoRenderResult(
            output_path=request.output_path,
            duration_seconds=metadata["duration"],
            command=tuple(command),
            width=metadata["width"],
            height=metadata["height"],
            fps=metadata["fps"],
            has_audio=metadata["has_audio"],
        )

    async def _probe_duration(self, path: Path) -> float:
        result = await self._run_probe(
            [
                self._ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ]
        )
        duration = float(json.loads(result)["format"]["duration"])
        if duration <= 0:
            raise RuntimeError("Voiceover has an invalid duration")
        return duration

    async def _probe_media(self, path: Path) -> MediaProbe:
        result = await self._run_probe(
            [
                self._ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,width,height,r_frame_rate",
                "-of",
                "json",
                str(path),
            ]
        )
        data = json.loads(result)
        streams = data.get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        if video is None:
            raise RuntimeError("Rendered video has no video stream")
        numerator, _, denominator = str(video.get("r_frame_rate", "0/1")).partition("/")
        fps = float(numerator) / float(denominator or 1)
        return {
            "duration": float(data["format"]["duration"]),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "fps": fps,
            "has_audio": any(item.get("codec_type") == "audio" for item in streams),
        }

    async def _run_probe(self, command: list[str]) -> str:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError("FFprobe timed out") from exc
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"FFprobe failed with exit code {process.returncode}: {message}")
        return stdout.decode("utf-8")
