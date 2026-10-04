from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.infrastructure.providers.youtube_analytics import YouTubeAnalyticsAdapter


@pytest.mark.asyncio
async def test_fetch_video_performance_maps_youtube_metrics() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "test-token"})
        return httpx.Response(
            200,
            json={
                "columnHeaders": [
                    {"name": "views"},
                    {"name": "likes"},
                    {"name": "comments"},
                    {"name": "shares"},
                    {"name": "subscribersGained"},
                    {"name": "estimatedMinutesWatched"},
                    {"name": "averageViewDuration"},
                    {"name": "averageViewPercentage"},
                ],
                "rows": [[1200, 80, 12, 5, 7, 15.5, 18.0, 72.5]],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = YouTubeAnalyticsAdapter(
        "client-id",
        "client-secret",
        "refresh-token",
        client=client,
    )
    measured_at = datetime(2026, 10, 4, 18, 30, tzinfo=UTC)

    try:
        result = await adapter.fetch_video_performance(
            publication_id="publication-1",
            platform_post_id="video-123",
            measured_at=measured_at,
        )
    finally:
        await client.aclose()

    assert result.platform == "youtube"
    assert result.views == 1200
    assert result.likes == 80
    assert result.comments == 12
    assert result.shares == 5
    assert result.subscribers_gained == 7
    assert result.watch_time_seconds == 930.0
    assert result.average_view_duration_seconds == 18.0
    assert result.retention == 0.725
    assert len(calls) == 2

    analytics_request = calls[1]
    assert analytics_request.headers["authorization"] == "Bearer test-token"
    assert analytics_request.url.params["filters"] == "video==video-123"
    assert analytics_request.url.params["startDate"] == "2026-10-04"
    assert analytics_request.url.params["endDate"] == "2026-10-04"


@pytest.mark.asyncio
async def test_adapter_requires_oauth_credentials() -> None:
    with pytest.raises(ValueError, match="OAuth credentials"):
        YouTubeAnalyticsAdapter("", "secret", "refresh")


@pytest.mark.asyncio
async def test_adapter_rejects_empty_analytics_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "test-token"})
        return httpx.Response(200, json={"rows": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = YouTubeAnalyticsAdapter(
        "client-id",
        "client-secret",
        "refresh-token",
        client=client,
    )

    try:
        with pytest.raises(RuntimeError, match="no metric rows"):
            await adapter.fetch_video_performance(
                publication_id="publication-1",
                platform_post_id="video-123",
                measured_at=datetime.now(UTC),
            )
    finally:
        await client.aclose()
