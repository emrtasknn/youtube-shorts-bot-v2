from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from app.application.ports.video_engine import VideoEngine, VideoRenderRequest, VideoRenderResult


class AtomicVideoEngine:
    """Wrap a validated video engine with Otopilot-style atomic publication.

    Rendering happens beside the destination under a unique temporary name.
    The previous successful MP4 remains untouched until the delegate has
    completed its own FFprobe and quality checks. os.replace then publishes
    the complete file atomically on the same filesystem.
    """

    def __init__(self, delegate: VideoEngine) -> None:
        self._delegate = delegate

    async def render(self, request: VideoRenderRequest) -> VideoRenderResult:
        destination = request.output_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged = destination.with_name(
            f".{destination.stem}.{uuid4().hex}.rendering{destination.suffix}"
        )
        staged_request = replace(request, output_path=staged)

        try:
            result = await self._delegate.render(staged_request)
            if not staged.is_file():
                raise RuntimeError("Video engine returned without a staged output file")
            if staged.stat().st_size <= 0:
                raise RuntimeError("Video engine produced an empty staged output")
            os.replace(staged, destination)
            return replace(result, output_path=destination)
        finally:
            staged.unlink(missing_ok=True)
            staged.with_suffix(".ass").unlink(missing_ok=True)
