from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class TextGenerationRequest:
    run_id: str
    request_id: str
    prompt: str
    system_instruction: str | None = None
    model: str | None = None
    generation_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TextGenerationResult:
    provider: str
    text: str
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TextGenerationGateway(Protocol):
    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult: ...
