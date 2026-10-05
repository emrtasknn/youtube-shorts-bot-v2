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


@dataclass(frozen=True, slots=True)
class PerformanceAggregate:
    """Aggregated measured performance for a stable production cohort."""

    category: str
    language: str
    production_strategy: str | None
    sample_count: int
    views_total: int
    likes_total: int
    comments_total: int
    shares_total: int
    subscribers_gained_total: int
    average_view_duration_seconds: Decimal | None = None
    average_retention: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.category:
            raise ValueError("category is required")
        if not self.language:
            raise ValueError("language is required")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        if (
            min(
                self.views_total,
                self.likes_total,
                self.comments_total,
                self.shares_total,
                self.subscribers_gained_total,
            )
            < 0
        ):
            raise ValueError("aggregate counts must be non-negative")
        if (
            self.average_view_duration_seconds is not None
            and self.average_view_duration_seconds < 0
        ):
            raise ValueError("average_view_duration_seconds must be non-negative")
        if self.average_retention is not None and not 0 <= self.average_retention <= 1:
            raise ValueError("average_retention must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class PerformanceBaseline:
    """Deterministic baseline metrics for a stable production cohort."""

    category: str
    language: str
    production_strategy: str | None
    sample_count: int
    average_views: Decimal
    average_likes: Decimal
    average_comments: Decimal
    average_shares: Decimal
    average_subscribers_gained: Decimal
    engagement_rate: Decimal
    subscriber_conversion_rate: Decimal
    average_view_duration_seconds: Decimal | None = None
    average_retention: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.category:
            raise ValueError("category is required")
        if not self.language:
            raise ValueError("language is required")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        if (
            min(
                self.average_views,
                self.average_likes,
                self.average_comments,
                self.average_shares,
                self.average_subscribers_gained,
                self.engagement_rate,
                self.subscriber_conversion_rate,
            )
            < 0
        ):
            raise ValueError("baseline metrics must be non-negative")
        if self.average_retention is not None and not 0 <= self.average_retention <= 1:
            raise ValueError("average_retention must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class PerformanceTimeSeriesPoint:
    """Deterministic point-in-time and growth features for a publication."""

    publication_id: UUID
    measured_at: datetime
    elapsed_hours: Decimal
    views: int
    likes: int
    comments: int
    shares: int
    subscribers_gained: int
    views_delta: int | None = None
    likes_delta: int | None = None
    comments_delta: int | None = None
    shares_delta: int | None = None
    subscribers_gained_delta: int | None = None
    views_per_hour: Decimal | None = None
    views_growth_rate: Decimal | None = None
    average_view_duration_seconds: Decimal | None = None
    retention: Decimal | None = None

    def __post_init__(self) -> None:
        if self.elapsed_hours < 0:
            raise ValueError("elapsed_hours must be non-negative")
        if min(self.views, self.likes, self.comments, self.shares, self.subscribers_gained) < 0:
            raise ValueError("snapshot counts must be non-negative")
        if self.elapsed_hours == 0 and self.views_per_hour is not None:
            raise ValueError("views_per_hour requires positive elapsed time")
        if self.views_growth_rate is not None and self.views_growth_rate < -1:
            raise ValueError("views_growth_rate cannot be less than -1")
        if (
            self.average_view_duration_seconds is not None
            and self.average_view_duration_seconds < 0
        ):
            raise ValueError("average_view_duration_seconds must be non-negative")
        if self.retention is not None and not 0 <= self.retention <= 1:
            raise ValueError("retention must be between 0 and 1")
