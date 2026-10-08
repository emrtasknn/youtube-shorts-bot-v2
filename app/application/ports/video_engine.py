from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.application.services.camera_motion import CameraMotionPlan


@dataclass(frozen=True, slots=True)
class VideoSceneInput:
    path: Path
    duration_seconds: float
    is_image: bool = False
    motion: CameraMotionPlan | None = None


@dataclass(frozen=True, slots=True)
class VideoRenderRequest:
    scenes: tuple[VideoSceneInput, ...]
    output_path: Path
    voiceover_path: Path | None = None
    background_audio_path: Path | None = None
    subtitle_text: str | None = None
    width: int = 1080
    height: int = 1920
    fps: int = 30
    background_volume: float = 0.18
    ducking_threshold: float = 0.03
    ducking_ratio: float = 8.0
    ducking_attack_ms: float = 20.0
    ducking_release_ms: float = 250.0


@dataclass(frozen=True, slots=True)
class VideoRenderResult:
    output_path: Path
    duration_seconds: float
    command: tuple[str, ...] = field(default_factory=tuple)
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False


class VideoEngine(Protocol):
    async def render(self, request: VideoRenderRequest) -> VideoRenderResult: ...
