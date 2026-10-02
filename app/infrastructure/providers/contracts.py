from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol


class ProviderCapability(StrEnum):
    TEXT_GENERATION = "TEXT_GENERATION"
    IMAGE_GENERATION = "IMAGE_GENERATION"
    VIDEO_GENERATION = "VIDEO_GENERATION"
    TTS = "TTS"
    STOCK_MEDIA = "STOCK_MEDIA"
    MUSIC = "MUSIC"
    SFX = "SFX"
    PUBLISH = "PUBLISH"
    ANALYTICS = "ANALYTICS"


class ErrorCategory(StrEnum):
    TRANSIENT = "TRANSIENT"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    AUTHENTICATION = "AUTHENTICATION"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    QUALITY = "QUALITY"
    PERMANENT = "PERMANENT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    request_id: str
    run_id: str
    capability: ProviderCapability
    operation: str
    provider: str
    payload: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    idempotency_key: str | None = None
    timeout_seconds: float = 60.0
    max_attempts: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_units: int = 0
    output_units: int = 0
    total_units: int = 0


@dataclass(frozen=True, slots=True)
class ProviderResult:
    success: bool
    provider: str
    request_id: str
    output: Any = None
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    cost: Decimal = Decimal("0")
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderError(Exception):
    code: str
    category: ErrorCategory
    provider: str
    message: str
    retryable: bool = False
    retry_after_seconds: float | None = None
    status_code: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.provider}:{self.code}: {self.message}"


class ProviderAdapter(Protocol):
    name: str
    capabilities: frozenset[ProviderCapability]

    async def execute(self, request: ProviderRequest) -> ProviderResult: ...


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    name: str
    capabilities: frozenset[ProviderCapability]
    priority: int = 0
    enabled: bool = True
