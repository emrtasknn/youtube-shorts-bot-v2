from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TTSRequest:
    run_id: str
    request_id: str
    text: str
    format: str = "mp3"
    model: str | None = None


@dataclass(frozen=True, slots=True)
class TTSResult:
    provider: str
    audio_bytes: bytes
    format: str
    metadata: dict[str, object] | None = None


class TTSGateway(Protocol):
    async def synthesize(self, request: TTSRequest) -> TTSResult: ...
