from pathlib import Path

import pytest

from app.application.ports.video_engine import (
    VideoRenderRequest,
    VideoRenderResult,
    VideoSceneInput,
)
from app.infrastructure.video.atomic import AtomicVideoEngine


class SuccessfulEngine:
    async def render(self, request: VideoRenderRequest) -> VideoRenderResult:
        request.output_path.write_bytes(b"new-valid-mp4")
        return VideoRenderResult(
            output_path=request.output_path,
            duration_seconds=3.0,
            width=1080,
            height=1920,
            fps=30.0,
            has_audio=True,
        )


class FailingEngine:
    async def render(self, request: VideoRenderRequest) -> VideoRenderResult:
        request.output_path.write_bytes(b"partial")
        raise RuntimeError("simulated render failure")


def request_for(path: Path) -> VideoRenderRequest:
    scene = path.parent / "scene.jpg"
    scene.write_bytes(b"fixture")
    return VideoRenderRequest(
        scenes=(VideoSceneInput(scene, 3.0, is_image=True),),
        output_path=path,
    )


@pytest.mark.asyncio
async def test_atomic_engine_publishes_only_completed_output(tmp_path: Path) -> None:
    destination = tmp_path / "short.mp4"
    request = request_for(destination)

    result = await AtomicVideoEngine(SuccessfulEngine()).render(request)

    assert destination.read_bytes() == b"new-valid-mp4"
    assert result.output_path == destination
    assert not list(tmp_path.glob("*.rendering.mp4"))
    assert not list(tmp_path.glob(".*.rendering.mp4"))


@pytest.mark.asyncio
async def test_atomic_engine_preserves_previous_output_on_failure(tmp_path: Path) -> None:
    destination = tmp_path / "short.mp4"
    destination.write_bytes(b"previous-good-video")
    request = request_for(destination)

    with pytest.raises(RuntimeError, match="simulated render failure"):
        await AtomicVideoEngine(FailingEngine()).render(request)

    assert destination.read_bytes() == b"previous-good-video"
    assert not list(tmp_path.glob(".*.rendering.mp4"))


@pytest.mark.asyncio
async def test_atomic_engine_rejects_missing_staged_output(tmp_path: Path) -> None:
    class MissingEngine:
        async def render(self, request: VideoRenderRequest) -> VideoRenderResult:
            return VideoRenderResult(output_path=request.output_path, duration_seconds=0)

    destination = tmp_path / "short.mp4"
    with pytest.raises(RuntimeError, match="without a staged output"):
        await AtomicVideoEngine(MissingEngine()).render(request_for(destination))
    assert not destination.exists()
