from __future__ import annotations

from pathlib import Path

import httpx

from app.application.ports.publisher import PublicationRequest, PublicationResult


class YouTubePublisher:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        if not all((client_id, client_secret, refresh_token)):
            raise ValueError(
                "YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN are required"
            )
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token

    async def _access_token(self) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError(f"YouTube OAuth refresh did not return an access token: {payload}")
        return str(token)

    async def publish(self, request: PublicationRequest) -> PublicationResult:
        path = Path(request.video_path)
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Video does not exist or is empty: {path}")
        token = await self._access_token()
        metadata = {
            "snippet": {
                "title": request.title[:100],
                "description": request.description,
                "categoryId": request.category_id,
                "defaultLanguage": "tr",
            },
            "status": {
                "privacyStatus": request.privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(path.stat().st_size),
            "X-Upload-Content-Type": "video/mp4",
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://www.googleapis.com/upload/youtube/v3/videos",
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers=headers,
                json=metadata,
            )
            response.raise_for_status()
            upload_url = response.headers.get("location")
            if not upload_url:
                raise RuntimeError("YouTube did not return a resumable upload URL")
            with path.open("rb") as video:
                upload = await client.put(
                    upload_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "video/mp4",
                        "Content-Length": str(path.stat().st_size),
                    },
                    content=video.read(),
                )
            upload.raise_for_status()
            payload = upload.json()
        video_id = str(payload.get("id") or "")
        if not video_id:
            raise RuntimeError(f"YouTube upload response has no video id: {payload}")
        actual_privacy = str(
            payload.get("status", {}).get("privacyStatus") or request.privacy_status
        )
        return PublicationResult(
            provider="youtube",
            platform_post_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            privacy_status=actual_privacy,
        )
