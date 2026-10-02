# M3 — FFmpeg Video Engine

FFmpeg is implemented as a local infrastructure adapter rather than an external provider.

## Responsibilities

- Render vertical 9:16 video at 1080x1920.
- Accept ordered image and video scene inputs.
- Normalize scenes with scale/crop, SAR normalization and a fixed FPS.
- Concatenate scenes deterministically.
- Optionally attach a TTS/voiceover audio track.
- Execute FFmpeg without a shell.
- Fail explicitly on timeout, non-zero exit code or missing output.

## Boundary

Application code depends on the VideoEngine protocol and render DTOs. It does not call subprocess or FFmpeg directly.

## Security

asyncio.create_subprocess_exec receives each command argument separately. User-controlled paths are never interpolated into a shell command.

## M4

The engine will be connected to the asset planner, Fish Audio TTS output and QC stage in the CUSTOM -> YouTube vertical slice.
