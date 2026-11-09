"""YouTube publishing for Studio.

Flow: upload as **private** right after render (with tags, thumbnail, comment),
send the preview to Telegram, and only flip it to **public** when the admin taps
"Yayınla", or let YouTube do it at a set time ("Planla", ``status.publishAt``).
Reject deletes the private upload. No large file has to travel
between the renderer (GitHub Actions or local) and the bot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.application.ports.publisher import PublicationRequest
from app.infrastructure.providers.youtube import YouTubePublisher, YouTubePublishError
from app.studio.models import Project

API = "https://www.googleapis.com/youtube/v3"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3"


def _api_message(r: httpx.Response) -> str:
    try:
        return str(r.json().get("error", {}).get("message", ""))[:200]
    except ValueError:
        return r.text[:200]


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

    async def check(self) -> str:
        """Refresh the token and read the channel name: a fast test of the credentials."""
        token = await self._token()
        r = await self._call(
            "GET", f"{API}/channels", token, params={"part": "snippet", "mine": "true"}
        )
        if r.status_code >= 400:
            raise YouTubePublishError(
                f"Token çalışıyor ama kanal okunamadı (HTTP {r.status_code}): {_api_message(r)}",
                retryable=False,
            )
        items = r.json().get("items") or []
        if not items:
            raise YouTubePublishError(
                "Bu Google hesabında YouTube kanalı yok; token'ı kanalın hesabıyla al.",
                retryable=False,
            )
        return str(items[0].get("snippet", {}).get("title", "?"))

    async def schedule(self, video_id: str, publish_at: str) -> None:
        """Keep the video private and let YouTube make it public at ``publish_at`` (UTC)."""
        token = await self._token()
        r = await self._call(
            "PUT",
            f"{API}/videos",
            token,
            params={"part": "status"},
            json={
                "id": video_id,
                "status": {
                    "privacyStatus": "private",
                    "publishAt": publish_at,
                    "selfDeclaredMadeForKids": False,
                },
            },
        )
        if r.status_code >= 400:
            raise YouTubePublishError(
                f"Planlanamadı (HTTP {r.status_code}): {_api_message(r)}", retryable=False
            )

    async def add_comment(self, video_id: str, text: str) -> str:
        token = await self._token()
        return await self._comment(token, video_id, text)

    async def _comment(self, token: str, video_id: str, text: str) -> str:
        c = await self._call(
            "POST",
            f"{API}/commentThreads",
            token,
            params={"part": "snippet"},
            json={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": text}},
                }
            },
        )
        if c.status_code >= 400:
            return f"Yorum eklenemedi (HTTP {c.status_code}): {_api_message(c)}"
        return "Yorum eklendi — sabitlemeyi YouTube uygulamasından yap (API izin vermiyor)"

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
            warnings.append(await self._comment(token, video_id, pinned_comment))
        return warnings

    async def delete(self, video_id: str) -> None:
        token = await self._token()
        r = await self._call("DELETE", f"{API}/videos", token, params={"id": video_id})
        if r.status_code not in (204, 404):
            r.raise_for_status()
