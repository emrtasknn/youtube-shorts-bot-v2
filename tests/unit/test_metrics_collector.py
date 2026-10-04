from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.ports.analytics import VideoPerformance
from app.application.services.metrics_collector import (
    MetricsCollectionRequest,
    MetricsCollector,
)


class FakeAnalyticsProvider:
    def __init__(self, performance: VideoPerformance) -> None:
        self.performance = performance
        self.calls: list[dict[str, Any]] = []

    async def fetch_video_performance(
        self,
        *,
        publication_id: str,
        platform_post_id: str,
        measured_at: datetime,
    ) -> VideoPerformance:
        self.calls.append(
            {
                "publication_id": publication_id,
                "platform_post_id": platform_post_id,
                "measured_at": measured_at,
            }
        )
        return self.performance


class FakeSnapshotService:
    def __init__(self) -> None:
        self.saved: list[VideoPerformance] = []

    def save(self, performance: VideoPerformance) -> VideoPerformance:
        self.saved.append(performance)
        return performance


@pytest.mark.asyncio
async def test_collector_fetches_and_persists_performance() -> None:
    measured_at = datetime(2026, 10, 4, 18, 30, tzinfo=UTC)
    performance = VideoPerformance(
        publication_id="publication-1",
        platform="youtube",
        platform_post_id="video-123",
        measured_at=measured_at,
        views=1200,
        likes=80,
    )
    provider = FakeAnalyticsProvider(performance)
    snapshots = FakeSnapshotService()

    collector = MetricsCollector(provider, snapshots)

    result = await collector.collect(
        MetricsCollectionRequest(
            publication_id="publication-1",
            platform_post_id="video-123",
            measured_at=measured_at,
        )
    )

    assert result == performance
    assert provider.calls == [
        {
            "publication_id": "publication-1",
            "platform_post_id": "video-123",
            "measured_at": measured_at,
        }
    ]
    assert snapshots.saved == [performance]


@pytest.mark.asyncio
async def test_collector_rejects_missing_publication_id() -> None:
    provider = FakeAnalyticsProvider(
        VideoPerformance(
            publication_id="publication-1",
            platform="youtube",
            platform_post_id="video-123",
            measured_at=datetime.now(UTC),
        )
    )
    collector = MetricsCollector(provider, FakeSnapshotService())

    with pytest.raises(ValueError, match="publication_id"):
        await collector.collect(
            MetricsCollectionRequest(
                publication_id="",
                platform_post_id="video-123",
                measured_at=datetime.now(UTC),
            )
        )


@pytest.mark.asyncio
async def test_collector_does_not_persist_when_provider_fails() -> None:
    class FailingProvider:
        async def fetch_video_performance(
            self,
            *,
            publication_id: str,
            platform_post_id: str,
            measured_at: datetime,
        ) -> VideoPerformance:
            raise RuntimeError("analytics provider unavailable")

    snapshots = FakeSnapshotService()
    collector = MetricsCollector(FailingProvider(), snapshots)

    with pytest.raises(RuntimeError, match="analytics provider unavailable"):
        await collector.collect(
            MetricsCollectionRequest(
                publication_id="publication-1",
                platform_post_id="video-123",
                measured_at=datetime.now(UTC),
            )
        )

    assert snapshots.saved == []
