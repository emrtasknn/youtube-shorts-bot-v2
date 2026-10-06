from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.application.ports.publisher import PublicationRequest
from app.infrastructure.providers.youtube import YouTubePublishError, YouTubePublisher


def request_for(path: Path, session_url: str | None = None, callback=None) -> PublicationRequest:
    return PublicationRequest(
        run_id="run-1",
        video_path=path,
        title="Test",
        description="Description",
        upload_session_url=session_url,
        upload_state_callback=callback,
    )


@pytest.mark.asyncio
async def test_youtube_publish_streams_chunks_and_persists_session(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"abcdefghij")
    calls: list[tuple[str, str]] = []
    states: list[tuple[str, int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            calls.append(("oauth", ""))
            return httpx.Response(200, json={"access_token": "token"})
        if request.method == "POST":
            calls.append(("init", ""))
            return httpx.Response(200, headers={"Location": "https://upload.test/session"})
        calls.append(("put", request.headers.get("content-range", "")))
        return httpx.Response(
            200,
            json={"id": "video-123", "status": {"privacyStatus": "public"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = YouTubePublisher(
        "client",
        "secret",
        "refresh",
        client=client,
        chunk_size=4,
    )
    try:
        result = await publisher.publish(
            request_for(video, callback=lambda url, offset, total: states.append((url, offset, total)))
        )
    finally:
        await client.aclose()

    assert result.platform_post_id == "video-123"
    assert result.url.endswith("video-123")
    assert calls == [
        ("oauth", ""),
        ("init", ""),
        ("put", "bytes 0-3/10"),
    ]
    assert states == [("https://upload.test/session", 0, 10), ("https://upload.test/session", 10, 10)]


@pytest.mark.asyncio
async def test_youtube_publish_resumes_from_persisted_session(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"abcdefghij")
    ranges: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "token"})
        if request.headers.get("content-range") == "bytes */10":
            return httpx.Response(308, headers={"Range": "bytes=0-3"})
        ranges.append(request.headers["content-range"])
        return httpx.Response(200, json={"id": "video-456", "status": {"privacyStatus": "public"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = YouTubePublisher("client", "secret", "refresh", client=client, chunk_size=4)
    try:
        result = await publisher.publish(
            request_for(video, "https://upload.test/session")
        )
    finally:
        await client.aclose()

    assert result.platform_post_id == "video-456"
    assert ranges == ["bytes 4-7/10"]


@pytest.mark.asyncio
async def test_youtube_publish_recovers_transient_chunk_failure_from_server_range(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"abcdefghij")
    attempts = 0
    ranges: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "token"})
        if request.headers.get("content-range") == "bytes */10":
            return httpx.Response(308, headers={"Range": "bytes=0-3"})
        attempts += 1
        ranges.append(request.headers["content-range"])
        if attempts == 1:
            return httpx.Response(500)
        return httpx.Response(200, json={"id": "video-789", "status": {"privacyStatus": "public"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = YouTubePublisher("client", "secret", "refresh", client=client, chunk_size=4)
    try:
        result = await publisher.publish(request_for(video, "https://upload.test/session"))
    finally:
        await client.aclose()

    assert result.platform_post_id == "video-789"
    assert ranges == ["bytes 4-7/10", "bytes 4-7/10"]


@pytest.mark.asyncio
async def test_youtube_publish_rejects_unknown_outcome_when_session_is_gone(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"abcdefgh")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = YouTubePublisher("client", "secret", "refresh", client=client)
    try:
        with pytest.raises(YouTubePublishError) as error:
            await publisher.publish(request_for(video, "https://upload.test/session"))
    finally:
        await client.aclose()

    assert error.value.retryable is False
    assert "outcome is unknown" in str(error.value)


@pytest.mark.asyncio
async def test_youtube_publish_does_not_load_entire_file(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"abcdefghij")

    received_sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "token"})
        if request.method == "POST":
            return httpx.Response(200, headers={"Location": "https://upload.test/session"})
        received_sizes.append(len(request.content))
        return httpx.Response(200, json={"id": "video-999", "status": {"privacyStatus": "public"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = YouTubePublisher("client", "secret", "refresh", client=client, chunk_size=3)
    try:
        await publisher.publish(request_for(video))
    finally:
        await client.aclose()

    assert received_sizes == [3]
