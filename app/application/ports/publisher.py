from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PublicationRequest:
    run_id: str
    video_path: Path
    title: str
    description: str
    privacy_status: str = "public"
    category_id: str = "27"
    upload_session_url: str | None = None
    upload_state_callback: Callable[[str, int, int], None] | None = None


@dataclass(frozen=True, slots=True)
class PublicationResult:
    provider: str
    platform_post_id: str
    url: str
    privacy_status: str


class Publisher(Protocol):
    async def publish(self, request: PublicationRequest) -> PublicationResult: ...
