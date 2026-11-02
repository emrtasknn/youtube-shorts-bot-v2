from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

from app.application.ports.asset_downloader import AssetDownloader


class CachedAssetDownloader:
    """Content-verified URL cache with atomic cache and destination publication."""

    def __init__(self, delegate: AssetDownloader, cache_dir: Path) -> None:
        self._delegate = delegate
        self._cache_dir = cache_dir
        self._locks: dict[str, asyncio.Lock] = {}

    async def download(self, url: str, destination: Path) -> None:
        if not url.strip():
            raise ValueError("Asset download URL must not be empty")

        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        suffix = destination.suffix.lower()
        if len(suffix) > 12 or not suffix.replace(".", "").isalnum():
            suffix = ".asset"
        cache_key = f"{key}{suffix}"
        cache_path = self._cache_dir / f"{cache_key}"
        manifest_path = self._cache_dir / f"{cache_key}.json"

        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            if not self._is_valid_entry(cache_path, manifest_path, url):
                await self._populate_cache(url, cache_path, manifest_path, cache_key)

            destination.parent.mkdir(parents=True, exist_ok=True)
            staged_destination = destination.with_name(
                f".{destination.name}.{uuid4().hex}.download"
            )
            try:
                shutil.copyfile(cache_path, staged_destination)
                if staged_destination.stat().st_size <= 0:
                    raise RuntimeError("Cached asset copy is empty")
                os.replace(staged_destination, destination)
            finally:
                staged_destination.unlink(missing_ok=True)

    def _is_valid_entry(self, cache_path: Path, manifest_path: Path, url: str) -> bool:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("url") != url or not cache_path.is_file():
                return False
            if cache_path.stat().st_size != manifest.get("size_bytes"):
                return False
            digest = hashlib.sha256(cache_path.read_bytes()).hexdigest()
            return digest == manifest.get("sha256")
        except (OSError, ValueError, TypeError):
            return False

    async def _populate_cache(
        self,
        url: str,
        cache_path: Path,
        manifest_path: Path,
        cache_key: str,
    ) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        staged_asset = self._cache_dir / f".{cache_key}.{uuid4().hex}.part"
        staged_manifest = self._cache_dir / f".{cache_key}.{uuid4().hex}.json"
        try:
            await self._delegate.download(url, staged_asset)
            if not staged_asset.is_file() or staged_asset.stat().st_size <= 0:
                raise RuntimeError("Asset provider returned an empty download")
            payload = staged_asset.read_bytes()
            manifest = {
                "schema_version": 1,
                "url": url,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            staged_manifest.write_text(
                json.dumps(manifest, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(staged_asset, cache_path)
            os.replace(staged_manifest, manifest_path)
        finally:
            staged_asset.unlink(missing_ok=True)
            staged_manifest.unlink(missing_ok=True)
