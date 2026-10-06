from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx

from app.application.ports.publisher import PublicationRequest, PublicationResult


class YouTubePublishError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        upload_session_url: str | None = None,
        bytes_uploaded: int = 0,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.upload_session_url = upload_session_url
        self.bytes_uploaded = bytes_uploaded


class YouTubePublisher:
    _INIT_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
    _CHUNK_SIZE = 8 * 1024 * 1024
    _MAX_CHUNK_ATTEMPTS = 3

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        *,
        client: httpx.AsyncClient | None = None,
        chunk_size: int = _CHUNK_SIZE,
    ) -> None:
        if not all((client_id, client_secret, refresh_token)):
            raise ValueError(
                "YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN are required"
            )
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._client = client
        self._chunk_size = chunk_size

    async def _access_token(self) -> str:
        client = self._client or httpx.AsyncClient(timeout=30.0)
        owned = self._client is None
        try:
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
        finally:
            if owned:
                await client.aclose()
        token = payload.get("access_token")
        if not token:
            raise YouTubePublishError(
                "YouTube OAuth refresh did not return an access token",
                retryable=False,
            )
        return str(token)

    async def publish(self, request: PublicationRequest) -> PublicationResult:
        path = Path(request.video_path)
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Video does not exist or is empty: {path}")

        total_bytes = path.stat().st_size
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

        client = self._client or httpx.AsyncClient(timeout=120.0)
        owned = self._client is None
        upload_url = request.upload_session_url
        try:
            is_new_session = request.upload_session_url is None
            if upload_url is None:
                upload_url = await self._initiate(client, token, metadata, total_bytes)

            offset = 0
            if not is_new_session:
                offset = (
                    await self._query_session(client, token, upload_url, total_bytes, initial=False)
                ) or 0

            if not is_new_session and offset >= total_bytes:
                completed = await self._query_completion(client, token, upload_url, total_bytes)
                if completed is not None:
                    return self._result(completed, request)

            if request.upload_session_url is None:
                offset = 0

            if request.upload_state_callback is not None:
                request.upload_state_callback(upload_url, offset, total_bytes)

            with path.open("rb") as video:
                video.seek(offset)
                while offset < total_bytes:
                    chunk = video.read(min(self._chunk_size, total_bytes - offset))
                    if not chunk:
                        raise YouTubePublishError(
                            "Video ended before the expected byte count",
                            retryable=False,
                            upload_session_url=upload_url,
                            bytes_uploaded=offset,
                        )
                    end = offset + len(chunk) - 1
                    offset, payload = await self._upload_chunk(
                        client,
                        token,
                        upload_url,
                        chunk,
                        offset,
                        end,
                        total_bytes,
                        request.upload_state_callback,
                    )
                    if payload is not None:
                        return self._result(payload, request)

            raise YouTubePublishError(
                "YouTube upload ended without a completion response",
                retryable=False,
                upload_session_url=upload_url,
                bytes_uploaded=offset,
            )
        except YouTubePublishError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise YouTubePublishError(
                f"YouTube upload transport failure: {exc}",
                retryable=True,
                upload_session_url=upload_url,
            ) from exc
        finally:
            if owned:
                await client.aclose()

    async def _initiate(
        self,
        client: httpx.AsyncClient,
        token: str,
        metadata: dict[str, object],
        total_bytes: int,
    ) -> str:
        try:
            response = await client.post(
                self._INIT_URL,
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Length": str(total_bytes),
                    "X-Upload-Content-Type": "video/mp4",
                },
                json=metadata,
            )
            if response.status_code >= 500 or response.status_code == 429:
                raise YouTubePublishError(
                    f"YouTube upload initiation failed with HTTP {response.status_code}",
                    retryable=True,
                )
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise YouTubePublishError(
                f"YouTube upload initiation transport failure: {exc}",
                retryable=True,
            ) from exc
        upload_url = response.headers.get("location")
        if not upload_url:
            raise YouTubePublishError(
                "YouTube did not return a resumable upload URL",
                retryable=False,
            )
        return upload_url

    async def _upload_chunk(
        self,
        client: httpx.AsyncClient,
        token: str,
        upload_url: str,
        chunk: bytes,
        offset: int,
        end: int,
        total_bytes: int,
        callback: Callable[[str, int, int], None] | None,
    ) -> tuple[int, dict[str, object] | None]:
        current_offset = offset
        for attempt in range(1, self._MAX_CHUNK_ATTEMPTS + 1):
            try:
                response = await client.put(
                    upload_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {current_offset}-{end}/{total_bytes}",
                    },
                    content=chunk,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                recovered = await self._query_session(
                    client, token, upload_url, total_bytes, initial=False
                )
                if recovered is not None:
                    current_offset = recovered
                    if callback is not None:
                        callback(upload_url, current_offset, total_bytes)
                    if current_offset >= total_bytes:
                        return current_offset, None
                if attempt == self._MAX_CHUNK_ATTEMPTS:
                    raise YouTubePublishError(
                        f"YouTube upload transport failure: {exc}",
                        retryable=True,
                        upload_session_url=upload_url,
                        bytes_uploaded=current_offset,
                    ) from exc
                continue

            if response.status_code in {200, 201}:
                payload = response.json()
                if callback is not None:
                    callback(upload_url, total_bytes, total_bytes)
                return total_bytes, payload

            if response.status_code == 308:
                current_offset = self._range_offset(response.headers.get("range"), current_offset)
                if callback is not None:
                    callback(upload_url, current_offset, total_bytes)
                return current_offset, None

            if response.status_code in {408, 429} or response.status_code >= 500:
                recovered = await self._query_session(
                    client, token, upload_url, total_bytes, initial=False
                )
                if recovered is not None:
                    current_offset = recovered
                    if callback is not None:
                        callback(upload_url, current_offset, total_bytes)
                    if current_offset >= total_bytes:
                        return current_offset, None
                if attempt == self._MAX_CHUNK_ATTEMPTS:
                    raise YouTubePublishError(
                        f"YouTube upload failed with HTTP {response.status_code}",
                        retryable=True,
                        upload_session_url=upload_url,
                        bytes_uploaded=current_offset,
                    )
                continue

            raise YouTubePublishError(
                f"YouTube upload failed with HTTP {response.status_code}",
                retryable=False,
                upload_session_url=upload_url,
                bytes_uploaded=current_offset,
            )
        raise AssertionError("unreachable")

    async def _query_session(
        self,
        client: httpx.AsyncClient,
        token: str,
        upload_url: str,
        total_bytes: int,
        *,
        initial: bool,
    ) -> int | None:
        try:
            response = await client.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Length": "0",
                    "Content-Range": f"bytes */{total_bytes}",
                },
                content=b"",
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            return None
        if response.status_code == 308:
            return self._range_offset(response.headers.get("range"), 0)
        if response.status_code in {200, 201}:
            return total_bytes
        if response.status_code == 404 and not initial:
            raise YouTubePublishError(
                "YouTube resumable upload session is gone; upload outcome is unknown",
                retryable=False,
                upload_session_url=upload_url,
            )
        if response.status_code == 404 and initial:
            return 0
        if response.status_code in {408, 429} or response.status_code >= 500:
            return None
        response.raise_for_status()
        return 0

    async def _query_completion(
        self,
        client: httpx.AsyncClient,
        token: str,
        upload_url: str,
        total_bytes: int,
    ) -> dict[str, object] | None:
        try:
            response = await client.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Length": "0",
                    "Content-Range": f"bytes */{total_bytes}",
                },
                content=b"",
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            return None
        if response.status_code in {200, 201}:
            return response.json()
        if response.status_code == 308:
            return None
        if response.status_code == 404:
            raise YouTubePublishError(
                "YouTube resumable upload session is gone; upload outcome is unknown",
                retryable=False,
                upload_session_url=upload_url,
            )
        return None

    @staticmethod
    def _range_offset(value: str | None, fallback: int) -> int:
        if not value:
            return fallback
        try:
            return int(value.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            return fallback

    @staticmethod
    def _result(payload: dict[str, object], request: PublicationRequest) -> PublicationResult:
        video_id = str(payload.get("id") or "")
        if not video_id:
            raise YouTubePublishError(
                "YouTube upload response has no video id",
                retryable=False,
            )
        status = payload.get("status")
        actual_privacy = (
            str(status.get("privacyStatus"))
            if isinstance(status, dict) and status.get("privacyStatus")
            else request.privacy_status
        )
        return PublicationResult(
            provider="youtube",
            platform_post_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            privacy_status=actual_privacy,
        )
