from __future__ import annotations

from datetime import datetime

import httpx

from app.application.ports.analytics import VideoPerformance


class YouTubeAnalyticsAdapter:
    """Fetches per-video metrics from the YouTube Analytics API."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        *,
        base_url: str = "https://youtubeanalytics.googleapis.com/v2",
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not all((client_id, client_secret, refresh_token)):
            raise ValueError("YouTube Analytics OAuth credentials are required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def fetch_video_performance(
        self,
        *,
        publication_id: str,
        platform_post_id: str,
        measured_at: datetime,
    ) -> VideoPerformance:
        if not publication_id:
            raise ValueError("publication_id is required")
        if not platform_post_id:
            raise ValueError("platform_post_id is required")

        token = await self._access_token()
        params = {
            "ids": "channel==MINE",
            "startDate": measured_at.date().isoformat(),
            "endDate": measured_at.date().isoformat(),
            "metrics": (
                "views,likes,comments,shares,subscribersGained,"
                "estimatedMinutesWatched,averageViewDuration,averageViewPercentage"
            ),
            "filters": f"video=={platform_post_id}",
        }
        response = await self._request(
            "GET",
            f"{self._base_url}/reports",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        payload = response.json()
        row = self._extract_row(payload)
        return VideoPerformance(
            publication_id=publication_id,
            platform="youtube",
            platform_post_id=platform_post_id,
            measured_at=measured_at,
            views=self._int_metric(row, 0),
            likes=self._int_metric(row, 1),
            comments=self._int_metric(row, 2),
            shares=self._int_metric(row, 3),
            subscribers_gained=self._int_metric(row, 4),
            watch_time_seconds=self._float_metric(row, 5, multiplier=60.0),
            average_view_duration_seconds=self._float_metric(row, 6),
            retention=self._float_metric(row, 7, multiplier=0.01),
        )

    async def _access_token(self) -> str:
        response = await self._request(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError(f"YouTube OAuth refresh did not return an access token: {payload}")
        return str(token)

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        if self._client is not None:
            response = await self._client.request(
                method,
                url,
                timeout=self._timeout_seconds,
                **kwargs,
            )
            response.raise_for_status()
            return response

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

    @staticmethod
    def _extract_row(payload: object) -> list[object]:
        if not isinstance(payload, dict):
            raise RuntimeError("YouTube Analytics response must be an object")
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("YouTube Analytics response contains no metric rows")
        row = rows[0]
        if not isinstance(row, list) or len(row) < 8:
            raise RuntimeError("YouTube Analytics response contains an invalid metric row")
        return row

    @staticmethod
    def _int_metric(row: list[object], index: int) -> int:
        try:
            return max(0, int(row[index]))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("YouTube Analytics returned an invalid integer metric") from exc

    @staticmethod
    def _float_metric(
        row: list[object],
        index: int,
        *,
        multiplier: float = 1.0,
    ) -> float:
        try:
            value = float(row[index]) * multiplier
        except (TypeError, ValueError) as exc:
            raise RuntimeError("YouTube Analytics returned an invalid numeric metric") from exc
        return max(0.0, value)
