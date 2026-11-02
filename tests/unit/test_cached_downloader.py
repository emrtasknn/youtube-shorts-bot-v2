from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from app.infrastructure.storage.cached_downloader import CachedAssetDownloader


class FakeDownloader:
    def __init__(self, payload: bytes = b"asset-bytes") -> None:
        self.payload = payload
        self.calls = 0

    async def download(self, url: str, destination: Path) -> None:
        self.calls += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.payload)


@pytest.mark.asyncio
async def test_cache_reuses_verified_asset_for_same_url(tmp_path: Path) -> None:
    delegate = FakeDownloader()
    downloader = CachedAssetDownloader(delegate, tmp_path / "cache")
    first = tmp_path / "one.jpg"
    second = tmp_path / "two.jpg"

    await downloader.download("https://assets.test/image.jpg", first)
    await downloader.download("https://assets.test/image.jpg", second)

    assert first.read_bytes() == b"asset-bytes"
    assert second.read_bytes() == b"asset-bytes"
    assert delegate.calls == 1


@pytest.mark.asyncio
async def test_cache_redownloads_when_cached_content_is_corrupted(tmp_path: Path) -> None:
    delegate = FakeDownloader()
    cache_dir = tmp_path / "cache"
    downloader = CachedAssetDownloader(delegate, cache_dir)
    destination = tmp_path / "image.jpg"
    url = "https://assets.test/image.jpg"

    await downloader.download(url, destination)
    cache_file = next(cache_dir.glob("*.jpg"))
    cache_file.write_bytes(b"corrupt")
    await downloader.download(url, destination)

    assert delegate.calls == 2
    assert destination.read_bytes() == b"asset-bytes"


@pytest.mark.asyncio
async def test_concurrent_requests_for_same_url_download_once(tmp_path: Path) -> None:
    delegate = FakeDownloader()
    downloader = CachedAssetDownloader(delegate, tmp_path / "cache")
    destinations = [tmp_path / f"{index}.jpg" for index in range(5)]

    await asyncio.gather(
        *(downloader.download("https://assets.test/shared.jpg", path) for path in destinations)
    )

    assert delegate.calls == 1
    assert all(path.read_bytes() == b"asset-bytes" for path in destinations)


@pytest.mark.asyncio
async def test_failed_download_preserves_existing_destination(tmp_path: Path) -> None:
    class BrokenDownloader:
        async def download(self, url: str, destination: Path) -> None:
            destination.write_bytes(b"")

    destination = tmp_path / "existing.jpg"
    destination.write_bytes(b"previous-valid")
    downloader = CachedAssetDownloader(BrokenDownloader(), tmp_path / "cache")

    with pytest.raises(RuntimeError, match="empty download"):
        await downloader.download("https://assets.test/broken.jpg", destination)

    assert destination.read_bytes() == b"previous-valid"
