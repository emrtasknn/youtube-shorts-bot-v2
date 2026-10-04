from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

from app.application.ports.analytics import AnalyticsProvider, VideoPerformance
from app.application.services.metrics_retry import (
    MetricsCollectionError,
    MetricsCollectionException,
    MetricsRetryPolicy,
)
from app.application.services.performance_snapshot import PerformanceSnapshotService


@dataclass(frozen=True, slots=True)
class MetricsCollectionRequest:
    publication_id: str
    platform_post_id: str
    measured_at: datetime


class MetricsCollector:
    """Collects analytics metrics and persists immutable performance snapshots."""

    def __init__(
        self,
        provider: AnalyticsProvider,
        snapshot_service: PerformanceSnapshotService,
    ) -> None:
        self._provider = provider
        self._snapshot_service = snapshot_service

    async def collect(self, request: MetricsCollectionRequest) -> VideoPerformance:
        if not request.publication_id:
            raise ValueError("publication_id is required")
        if not request.platform_post_id:
            raise ValueError("platform_post_id is required")

        try:
            performance = await self._provider.fetch_video_performance(
                publication_id=request.publication_id,
                platform_post_id=request.platform_post_id,
                measured_at=request.measured_at,
            )
        except Exception as exc:
            raise MetricsCollectionException(
                MetricsCollectionError(
                    kind=MetricsRetryPolicy.classify(exc),
                    code=self._error_code(exc),
                    message=str(exc),
                    attempts=1,
                )
            ) from exc

        return self._snapshot_service.save(performance)

    @staticmethod
    def _error_code(error: BaseException) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            return f"HTTP_{error.response.status_code}"
        if isinstance(error, httpx.TimeoutException):
            return "TIMEOUT"
        if isinstance(error, httpx.NetworkError):
            return "NETWORK_ERROR"
        if isinstance(error, ValueError):
            return "INVALID_RESPONSE"
        return "ANALYTICS_PROVIDER_ERROR"
