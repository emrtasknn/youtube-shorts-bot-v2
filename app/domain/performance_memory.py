from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PerformanceProductionFeatures:
    """Immutable production features used to interpret published performance."""

    category: str
    language: str
    topic: str
    angle: str | None = None
    hook: str | None = None
    duration_target_seconds: Decimal | None = None
    word_count: int | None = None
    scene_count: int | None = None
    visual_providers: tuple[str, ...] = ()
    tts_provider: str | None = None
    production_strategy: str | None = None

    def __post_init__(self) -> None:
        if not self.category:
            raise ValueError("category is required")
        if not self.language:
            raise ValueError("language is required")
        if not self.topic:
            raise ValueError("topic is required")
        if self.duration_target_seconds is not None and self.duration_target_seconds < 0:
            raise ValueError("duration_target_seconds must be non-negative")
        if self.word_count is not None and self.word_count < 0:
            raise ValueError("word_count must be non-negative")
        if self.scene_count is not None and self.scene_count < 0:
            raise ValueError("scene_count must be non-negative")
        if any(not provider for provider in self.visual_providers):
            raise ValueError("visual_providers must not contain empty values")


@dataclass(frozen=True, slots=True)
class PerformanceMemory:
    """Domain contract linking a publication to its immutable production features."""

    publication_id: UUID
    run_id: UUID
    content_id: UUID
    script_id: UUID
    platform: str
    platform_post_id: str
    published_at: datetime
    features: PerformanceProductionFeatures

    def __post_init__(self) -> None:
        if not self.platform:
            raise ValueError("platform is required")
        if not self.platform_post_id:
            raise ValueError("platform_post_id is required")
