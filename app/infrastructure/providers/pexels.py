from __future__ import annotations

from typing import Any

import httpx

from app.infrastructure.providers.contracts import (
    ErrorCategory,
    ProviderCapability,
    ProviderError,
    ProviderRequest,
    ProviderResult,
)


class PexelsStockMediaProvider:
    name = "pexels"
    capabilities = frozenset({ProviderCapability.STOCK_MEDIA})

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.pexels.com",
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Pexels API key must not be empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        if request.operation not in {"search_photos", "search_videos"}:
            raise ProviderError(
                code="UNSUPPORTED_OPERATION",
                category=ErrorCategory.INVALID_REQUEST,
                provider=self.name,
                message=f"Unsupported Pexels operation: {request.operation}",
            )

        query = str(request.payload.get("query", "")).strip()
        if not query:
            raise ProviderError(
                code="MISSING_QUERY",
                category=ErrorCategory.INVALID_REQUEST,
                provider=self.name,
                message="Pexels search requires a non-empty query",
            )

        params = self._search_params(request.payload, query)
        endpoint = "/v1/search" if request.operation == "search_photos" else "/v1/videos/search"
        response = await self._request(endpoint, params, request.timeout_seconds)

        return ProviderResult(
            success=True,
            provider=self.name,
            request_id=request.request_id,
            output={
                "operation": request.operation,
                "query": query,
                "page": response.get("page", 1),
                "per_page": response.get("per_page", 0),
                "total_results": response.get("total_results", 0),
                "items": self._normalize_items(
                    response.get(
                        "photos" if request.operation == "search_photos" else "videos",
                        [],
                    )
                ),
            },
            metadata={
                "source": "pexels",
                "attribution_required": True,
            },
        )

    async def _request(
        self, endpoint: str, params: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        headers = {"Authorization": self._api_key}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=timeout_seconds or self._timeout_seconds,
        )
        try:
            response = await client.get(endpoint, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                code="TIMEOUT",
                category=ErrorCategory.TIMEOUT,
                provider=self.name,
                message="Pexels request timed out",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                code="NETWORK_ERROR",
                category=ErrorCategory.TRANSIENT,
                provider=self.name,
                message="Pexels request failed before receiving a response",
                retryable=True,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if 200 <= response.status_code < 300:
            return response.json()

        raise self._provider_error(response)

    @staticmethod
    def _search_params(payload: dict[str, Any], query: str) -> dict[str, Any]:
        params: dict[str, Any] = {
            "query": query,
            "page": max(1, int(payload.get("page", 1))),
            "per_page": min(80, max(1, int(payload.get("per_page", 15)))),
        }
        for key in ("orientation", "size", "locale", "color"):
            value = payload.get(key)
            if value:
                params[key] = value
        return params

    def _provider_error(self, response: httpx.Response) -> ProviderError:
        retry_after = response.headers.get("Retry-After")
        retry_after_seconds = float(retry_after) if retry_after else None

        if response.status_code in {401, 403}:
            category = ErrorCategory.AUTHENTICATION
            retryable = False
        elif response.status_code == 429:
            category = ErrorCategory.RATE_LIMITED
            retryable = True
        elif 500 <= response.status_code <= 599:
            category = ErrorCategory.TRANSIENT
            retryable = True
        elif response.status_code == 404:
            category = ErrorCategory.NOT_FOUND
            retryable = False
        else:
            category = ErrorCategory.INVALID_REQUEST
            retryable = False

        return ProviderError(
            code=f"HTTP_{response.status_code}",
            category=category,
            provider=self.name,
            message=f"Pexels API returned HTTP {response.status_code}",
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
            status_code=response.status_code,
        )

    @staticmethod
    def _normalize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in items:
            src = item.get("src", {})
            normalized.append(
                {
                    "id": item.get("id"),
                    "type": "video" if "video_files" in item else "photo",
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "duration": item.get("duration"),
                    "source_url": item.get("url"),
                    "download_url": (
                        src.get("portrait") or src.get("large") or src.get("original")
                    ),
                    "photographer": item.get("photographer"),
                    "photographer_url": item.get("photographer_url"),
                    "alt": item.get("alt"),
                    "video_files": item.get("video_files"),
                }
            )
        return normalized
