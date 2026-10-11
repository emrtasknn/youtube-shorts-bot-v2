from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


class HttpAssetDownloader:
    def __init__(self, *, timeout_seconds: float = 60.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def download(self, url: str, destination: Path) -> None:
        if not url.strip():
            raise ValueError("Asset download URL must not be empty")
        destination.parent.mkdir(parents=True, exist_ok=True)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; YouTubeShortsBotV2/1.0; "
                "+https://github.com/emrtasknn/youtube-shorts-bot-v2)"
            ),
            "Referer": "https://commons.wikimedia.org/",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
            if response.status_code == 403:
                # Wikimedia API URLs can include tracking parameters that are not
                # needed to retrieve the original asset and may trigger edge blocks.
                parsed = urlsplit(url)
                clean_query = urlencode(
                    [
                        (key, value)
                        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                        if not key.lower().startswith("utm_")
                    ]
                )
                clean_url = urlunsplit(
                    (parsed.scheme, parsed.netloc, parsed.path, clean_query, parsed.fragment)
                )
                if clean_url != url:
                    response = await client.get(clean_url)
            response.raise_for_status()
            if not response.content:
                raise RuntimeError("Asset download returned an empty response")
            destination.write_bytes(response.content)
