from __future__ import annotations

import asyncio

from app.application.ports.video_engine import (
    VideoRenderRequest,
    VideoRenderResult,
)


class FFmpegCommandBuilder:
    def __init__(self, executable: str = "ffmpeg") -> None:
        self._executable = executable

    def build(self, request: VideoRenderRequest) -> list[str]:
        if not request.scenes:
            raise ValueError("At least one video scene is required")
        if request.width <= 0 or request.height <= 0:
            raise ValueError("Video dimensions must be positive")
        if request.fps <= 0:
            raise ValueError("Video FPS must be positive")

        for scene in request.scenes:
            if scene.duration_seconds <= 0:
                raise ValueError("Scene duration must be positive")
            if not scene.path.is_file():
                raise FileNotFoundError(scene.path)

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [self._executable, "-y", "-hide_banner", "-loglevel", "error"]
        filter_inputs: list[str] = []

        for index, scene in enumerate(request.scenes):
            if scene.is_image:
                command.extend(["-loop", "1", "-t", str(scene.duration_seconds)])
            command.extend(["-i", str(scene.path)])
            filter_inputs.append(
                f"[{index}:v]scale={request.width}:{request.height}:"
                f"force_original_aspect_ratio=increase,"
                f"crop={request.width}:{request.height},setsar=1,fps={request.fps},"
                f"trim=duration={scene.duration_seconds},setpts=PTS-STARTPTS[v{index}]"
            )

        audio_input_index: int | None = None
        if request.voiceover_path is not None:
            if not request.voiceover_path.is_file():
                raise FileNotFoundError(request.voiceover_path)
            audio_input_index = len(request.scenes)
            command.extend(["-i", str(request.voiceover_path)])

        concat_inputs = "".join(f"[v{index}]" for index in range(len(request.scenes)))
        filter_complex = ";".join(filter_inputs)
        filter_complex += (
            f";{concat_inputs}concat=n={len(request.scenes)}:v=1:a=0,format=yuv420p[vout]"
        )
        command.extend(["-filter_complex", filter_complex, "-map", "[vout]"])

        if audio_input_index is not None:
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
    def __init__(self, executable: str = "ffmpeg", *, timeout_seconds: float = 300.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("FFmpeg timeout must be positive")
        self._builder = FFmpegCommandBuilder(executable)
        self._timeout_seconds = timeout_seconds

    async def render(self, request: VideoRenderRequest) -> VideoRenderResult:
        command = self._builder.build(request)
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

        duration = sum(scene.duration_seconds for scene in request.scenes)
        return VideoRenderResult(
            output_path=request.output_path,
            duration_seconds=duration,
            command=tuple(command),
        )
