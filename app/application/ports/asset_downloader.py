from __future__ import annotations

from pathlib import Path
from typing import Protocol


class AssetDownloader(Protocol):
    async def download(self, url: str, destination: Path) -> None: ...
