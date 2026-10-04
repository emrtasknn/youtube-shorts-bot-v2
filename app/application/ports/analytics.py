from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class VideoPerformance:
    publication_id: str
    platform: str
    platform_post_id: str
    measured_at: datetime
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    subscribers_gained: int = 0
    watch_time_seconds: float | None = None
    average_view_duration_seconds: float | None = None
    retention: float | None = None

    def __post_init__(self) -> None:
        if not self.publication_id:
            raise ValueError("publication_id is required")
        if not self.platform:
            raise ValueError("platform is required")
        if not self.platform_post_id:
            raise ValueError("platform_post_id is required")
        if self.views < 0:
            raise ValueError("views must be non-negative")
        if self.likes < 0:
            raise ValueError("likes must be non-negative")
        if self.comments < 0:
            raise ValueError("comments must be non-negative")
        if self.shares < 0:
            raise ValueError("shares must be non-negative")
        if self.subscribers_gained < 0:
            raise ValueError("subscribers_gained must be non-negative")
        if self.watch_time_seconds is not None and self.watch_time_seconds < 0:
            raise ValueError("watch_time_seconds must be non-negative")
        if (
            self.average_view_duration_seconds is not None
            and self.average_view_duration_seconds < 0
        ):
            raise ValueError("average_view_duration_seconds must be non-negative")
        if self.retention is not None and not 0 <= self.retention <= 1:
            raise ValueError("retention must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "publication_id": self.publication_id,
            "platform": self.platform,
            "platform_post_id": self.platform_post_id,
            "measured_at": self.measured_at,
            "views": self.views,
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
            "subscribers_gained": self.subscribers_gained,
            "watch_time_seconds": self.watch_time_seconds,
            "average_view_duration_seconds": self.average_view_duration_seconds,
            "retention": self.retention,
        }
