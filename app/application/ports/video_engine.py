from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VideoSceneInput:
    path: Path
    duration_seconds: float
    is_image: bool = False


@dataclass(frozen=True, slots=True)
class VideoRenderRequest:
    scenes: tuple[VideoSceneInput, ...]
    output_path: Path
    voiceover_path: Path | None = None
    width: int = 1080
    height: int = 1920
    fps: int = 30


@dataclass(frozen=True, slots=True)
class VideoRenderResult:
    output_path: Path
    duration_seconds: float
    command: tuple[str, ...] = field(default_factory=tuple)


class VideoEngine(Protocol):
    async def render(self, request: VideoRenderRequest) -> VideoRenderResult: ...
