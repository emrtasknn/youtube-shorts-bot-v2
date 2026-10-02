from __future__ import annotations

from pathlib import Path

import httpx


class HttpAssetDownloader:
    def __init__(self, *, timeout_seconds: float = 60.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def download(self, url: str, destination: Path) -> None:
        if not url.strip():
            raise ValueError("Asset download URL must not be empty")
        destination.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds, follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            if not response.content:
                raise RuntimeError("Asset download returned an empty response")
            destination.write_bytes(response.content)
