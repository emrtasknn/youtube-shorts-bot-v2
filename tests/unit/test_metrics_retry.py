from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.application.ports.analytics import VideoPerformance
from app.application.services.metrics_collector import (
    MetricsCollectionRequest,
    MetricsCollector,
)
from app.application.services.metrics_retry import (
    MetricsCollectionException,
    MetricsFailureKind,
    MetricsRetryPolicy,
)


class FakeSnapshotService:
    def __init__(self) -> None:
        self.saved: list[VideoPerformance] = []

    def save(self, performance: VideoPerformance) -> VideoPerformance:
        self.saved.append(performance)
        return performance


def request() -> MetricsCollectionRequest:
    return MetricsCollectionRequest(
        publication_id="publication-1",
        platform_post_id="video-123",
        measured_at=datetime(2026, 10, 4, 18, 30, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_collector_classifies_timeout_as_retryable() -> None:
    class FailingProvider:
        async def fetch_video_performance(self, **kwargs: object) -> VideoPerformance:
            raise httpx.ReadTimeout("analytics timeout")

    snapshots = FakeSnapshotService()
    collector = MetricsCollector(FailingProvider(), snapshots)

    with pytest.raises(MetricsCollectionException) as exc_info:
        await collector.collect(request())

    assert exc_info.value.failure.kind == MetricsFailureKind.RETRYABLE
    assert exc_info.value.failure.code == "TIMEOUT"
    assert exc_info.value.failure.attempts == 1
    assert snapshots.saved == []


@pytest.mark.asyncio
async def test_collector_classifies_bad_request_as_permanent() -> None:
    class FailingProvider:
        async def fetch_video_performance(self, **kwargs: object) -> VideoPerformance:
            response = httpx.Response(400, request=httpx.Request("GET", "https://example.com"))
            raise httpx.HTTPStatusError("bad request", request=response.request, response=response)

    collector = MetricsCollector(FailingProvider(), FakeSnapshotService())

    with pytest.raises(MetricsCollectionException) as exc_info:
        await collector.collect(request())

    assert exc_info.value.failure.kind == MetricsFailureKind.PERMANENT
    assert exc_info.value.failure.code == "HTTP_400"


def test_retry_policy_marks_rate_limit_as_retryable() -> None:
    response = httpx.Response(429, request=httpx.Request("GET", "https://example.com"))
    error = httpx.HTTPStatusError("rate limited", request=response.request, response=response)

    assert MetricsRetryPolicy.classify(error) == MetricsFailureKind.RETRYABLE
