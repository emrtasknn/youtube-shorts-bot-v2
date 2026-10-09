from __future__ import annotations

import re
from html import unescape
from typing import Any

import httpx

from app.infrastructure.providers.contracts import (
    ErrorCategory,
    ProviderCapability,
    ProviderError,
    ProviderRequest,
    ProviderResult,
)


class WikimediaCommonsProvider:
    """Public Wikimedia Commons image search for archival and historical visuals."""

    name = "wikimedia_commons"
    capabilities = frozenset({ProviderCapability.STOCK_MEDIA})

    def __init__(
        self,
        *,
        base_url: str = "https://commons.wikimedia.org/w/api.php",
        timeout_seconds: float = 30.0,
        user_agent: str = "YouTubeShortsBotV2/1.0 (https://github.com/emrtasknn/youtube-shorts-bot-v2; contact: emretkn48@gmail.com)",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent
        self._client = client

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        if request.operation != "search_photos":
            raise ProviderError(
                code="UNSUPPORTED_OPERATION",
                category=ErrorCategory.INVALID_REQUEST,
                provider=self.name,
                message=f"Unsupported Wikimedia Commons operation: {request.operation}",
            )
        query = str(request.payload.get("query", "")).strip()
        if not query:
            raise ProviderError(
                code="MISSING_QUERY",
                category=ErrorCategory.INVALID_REQUEST,
                provider=self.name,
                message="Wikimedia Commons search requires a non-empty query",
            )

        per_page = min(50, max(1, int(request.payload.get("per_page", 15))))
        page = max(1, int(request.payload.get("page", 1)))
        params: dict[str, str | int] = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": 6,
            "gsrlimit": per_page,
            "gsroffset": (page - 1) * per_page,
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 1800,
            "format": "json",
            "formatversion": 2,
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            response = await client.get(
                self._base_url,
                params=params,
                headers={"User-Agent": self._user_agent},
                timeout=request.timeout_seconds or self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                code="TIMEOUT",
                category=ErrorCategory.TIMEOUT,
                provider=self.name,
                message="Wikimedia Commons request timed out",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                code="NETWORK_ERROR",
                category=ErrorCategory.TRANSIENT,
                provider=self.name,
                message="Wikimedia Commons request failed",
                retryable=True,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderError(
                code=f"HTTP_{response.status_code}",
                category=ErrorCategory.RATE_LIMITED
                if response.status_code == 429
                else ErrorCategory.TRANSIENT,
                provider=self.name,
                message=f"Wikimedia Commons API returned HTTP {response.status_code}",
                retryable=True,
                status_code=response.status_code,
            )
        if not 200 <= response.status_code < 300:
            # Preserve a short response excerpt: Wikimedia and edge proxies often
            # explain 403 blocks in the body, while the status alone is ambiguous.
            body_excerpt = " ".join(response.text.split())[:240]
            detail = f": {body_excerpt}" if body_excerpt else ""
            raise ProviderError(
                code=f"HTTP_{response.status_code}",
                category=ErrorCategory.INVALID_REQUEST,
                provider=self.name,
                message=(
                    f"Wikimedia Commons API returned HTTP {response.status_code}{detail}"
                ),
                status_code=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(
                code="INVALID_RESPONSE",
                category=ErrorCategory.QUALITY,
                provider=self.name,
                message="Wikimedia Commons API returned invalid JSON",
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderError(
                code="INVALID_RESPONSE",
                category=ErrorCategory.QUALITY,
                provider=self.name,
                message="Wikimedia Commons API returned a non-object JSON response",
            )

        query_data = payload.get("query") or {}
        pages = query_data.get("pages", []) if isinstance(query_data, dict) else []
        items = self._normalize_items(pages if isinstance(pages, list) else [])
        return ProviderResult(
            success=True,
            provider=self.name,
            request_id=request.request_id,
            output={
                "operation": request.operation,
                "query": query,
                "page": page,
                "per_page": per_page,
                "total_results": len(items),
                "items": items,
            },
            metadata={
                "source": "wikimedia_commons",
                "attribution_required": True,
                "license_check_required": True,
            },
        )

    @classmethod
    def _normalize_items(cls, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for page in pages:
            imageinfo = page.get("imageinfo") or []
            if not imageinfo or not isinstance(imageinfo[0], dict):
                continue
            info = imageinfo[0]
            mime = str(info.get("mime", ""))
            if mime and not mime.startswith("image/"):
                continue
            title = str(page.get("title", ""))
            extmetadata = info.get("extmetadata") or {}
            if not isinstance(extmetadata, dict):
                extmetadata = {}
            description = cls._metadata_text(extmetadata.get("ImageDescription"))
            artist = cls._metadata_text(extmetadata.get("Artist"))
            license_name = cls._metadata_text(extmetadata.get("LicenseShortName"))
            license_url = cls._metadata_text(extmetadata.get("LicenseUrl"))
            source_url = str(info.get("descriptionurl") or "")
            download_url = str(info.get("thumburl") or info.get("url") or "")
            width = info.get("thumbwidth") or info.get("width") or 0
            height = info.get("thumbheight") or info.get("height") or 0
            if not download_url or not source_url:
                continue
            normalized.append(
                {
                    "id": f"commons:{page.get('pageid', title)}",
                    "type": "photo",
                    "width": width,
                    "height": height,
                    "duration": None,
                    "source_url": source_url,
                    "download_url": download_url,
                    "photographer": artist,
                    "photographer_url": source_url,
                    "alt": f"{title.removeprefix('File:')}. {description}",
                    "title": title.removeprefix("File:"),
                    "description": description,
                    "license": license_name,
                    "license_url": license_url,
                    "attribution": f"{artist} — {license_name}" if artist else license_name,
                    "source": "wikimedia_commons",
                    "portrait_crop_allowed": True,
                }
            )
        return normalized

    @staticmethod
    def _metadata_text(value: Any) -> str:
        if isinstance(value, dict):
            value = value.get("value", "")
        text = unescape(str(value or ""))
        return " ".join(re.sub(r"<[^>]+>", " ", text).split())
