"""YouTube publishing for Studio.

Flow: upload as **private** right after render (with tags, thumbnail, comment),
send the preview to Telegram, and only flip it to **public** when the admin taps
"Yayınla". Reject deletes the private upload. No large file has to travel
between the renderer (GitHub Actions or local) and the bot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.application.ports.publisher import PublicationRequest
from app.infrastructure.providers.youtube import YouTubePublisher
from app.studio.models import Project

API = "https://www.googleapis.com/youtube/v3"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3"


@dataclass(slots=True)
class UploadResult:
    video_id: str
    url: str
    warnings: list[str]


class StudioYouTube:
    def __init__(
        self, client_id: str, client_secret: str, refresh_token: str, *, category_id: str = "27"
    ) -> None:
        self._uploader = YouTubePublisher(client_id, client_secret, refresh_token)
        self._category = category_id

    async def _token(self) -> str:
        return await self._uploader._access_token()

    async def _call(self, method: str, url: str, token: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.request(
                method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
        return r

    async def upload_private(
        self, project: Project, video: Path, thumbnail: Path | None
    ) -> UploadResult:
        result = await self._uploader.publish(
            PublicationRequest(
                run_id=project.id,
                video_path=video,
                title=project.title or project.topic,
                description=project.description,
                privacy_status="private",
                category_id=self._category,
            )
        )
        vid = result.platform_post_id
        token = await self._token()
        warnings: list[str] = []
        r = await self._call(
            "PUT",
            f"{API}/videos",
            token,
            params={"part": "snippet"},
            json={
                "id": vid,
                "snippet": {
                    "title": (project.title or project.topic)[:100],
                    "description": project.description,
                    "tags": project.tags[:30],
                    "categoryId": self._category,
                    "defaultLanguage": "tr",
                    "defaultAudioLanguage": "tr",
                },
            },
        )
        if r.status_code >= 400:
            warnings.append(f"Etiketler eklenemedi (HTTP {r.status_code})")
        if thumbnail is not None and thumbnail.is_file():
            r = await self._set_thumbnail(token, vid, thumbnail)
            if r.status_code >= 400:
                warnings.append(
                    "Thumbnail yüklenemedi (hesap doğrulaması gerekebilir ya da Shorts için "
                    f"desteklenmiyor, HTTP {r.status_code})"
                )
        return UploadResult(vid, f"https://youtube.com/shorts/{vid}", warnings)

    async def _set_thumbnail(self, token: str, video_id: str, path: Path) -> httpx.Response:
        async with httpx.AsyncClient(timeout=120) as client:
            return await client.post(
                f"{UPLOAD_API}/thumbnails/set",
                params={"videoId": video_id},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"},
                content=path.read_bytes(),
            )

    async def make_public(self, video_id: str, pinned_comment: str = "") -> list[str]:
        token = await self._token()
        warnings: list[str] = []
        r = await self._call(
            "PUT",
            f"{API}/videos",
            token,
            params={"part": "status"},
            json={
                "id": video_id,
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
            },
        )
        r.raise_for_status()
        if pinned_comment:
            c = await self._call(
                "POST",
                f"{API}/commentThreads",
                token,
                params={"part": "snippet"},
                json={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {"snippet": {"textOriginal": pinned_comment}},
                    }
                },
            )
            if c.status_code >= 400:
                warnings.append(f"Yorum eklenemedi (HTTP {c.status_code})")
            else:
                warnings.append(
                    "Yorum eklendi — sabitlemeyi YouTube uygulamasından yap (API izin vermiyor)"
                )
        return warnings

    async def delete(self, video_id: str) -> None:
        token = await self._token()
        r = await self._call("DELETE", f"{API}/videos", token, params={"id": video_id})
        if r.status_code not in (204, 404):
            r.raise_for_status()
