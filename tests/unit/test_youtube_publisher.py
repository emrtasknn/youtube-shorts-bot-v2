from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.application.ports.publisher import PublicationRequest
from app.infrastructure.providers.youtube import YouTubePublisher, YouTubePublishError


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
            request_for(
                video, callback=lambda url, offset, total: states.append((url, offset, total))
            )
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
    assert states == [
        ("https://upload.test/session", 0, 10),
        ("https://upload.test/session", 10, 10),
    ]


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
        result = await publisher.publish(request_for(video, "https://upload.test/session"))
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


@pytest.mark.asyncio
async def test_oauth_invalid_grant_is_explained() -> None:
    from app.infrastructure.providers.youtube import YouTubePublishError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_description": "Token has been expired or revoked.",
            },
        )

    publisher = YouTubePublisher(
        "client-id",
        "client-secret",
        "refresh-token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(YouTubePublishError) as info:
        await publisher._access_token()
    text = str(info.value)
    assert "invalid_grant" in text and "expired or revoked" in text
    assert "youtube_refresh_token.py" in text and "Publish app" in text
    assert "client-secret" not in text and "refresh-token" not in text
    assert info.value.retryable is False


def test_refresh_token_script_builds_offline_pkce_url() -> None:
    import importlib.util
    import urllib.parse
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "youtube_refresh_token.py"
    spec = importlib.util.spec_from_file_location("youtube_refresh_token", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    verifier, challenge = mod.pkce_pair()
    url = mod.build_auth_url("cid", "http://127.0.0.1:5555/", "st", challenge)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert q["code_challenge_method"] == ["S256"] and q["state"] == ["st"]
    assert "youtube.force-ssl" in q["scope"][0] and "youtube.upload" in q["scope"][0]
    assert verifier != challenge


@pytest.mark.asyncio
async def test_studio_schedule_and_check(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from app.studio.publisher import StudioYouTube

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path.endswith("/channels"):
            return httpx.Response(200, json={"items": [{"snippet": {"title": "Bir Garip Tarih"}}]})
        return httpx.Response(200, json={"id": "v1"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    yt = StudioYouTube("cid", "secret", "refresh")
    assert await yt.check() == "Bir Garip Tarih"
    await yt.schedule("v1", "2026-11-09T16:00:00Z")
    put = [r for r in seen if r.method == "PUT"][-1]
    assert put.url.params["part"] == "status"
    assert json.loads(put.content)["status"] == {
        "privacyStatus": "private",
        "publishAt": "2026-11-09T16:00:00Z",
        "selfDeclaredMadeForKids": False,
    }


@pytest.mark.asyncio
async def test_schedule_error_is_explained_in_turkish(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.studio.publisher import StudioYouTube

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "The request metadata specifies an invalid scheduled publishing time."
                }
            },
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    with pytest.raises(YouTubePublishError, match="daha önce herkese açıldıysa"):
        await StudioYouTube("c", "s", "r").schedule("v1", "2026-11-09T18:00:00Z")


@pytest.mark.asyncio
async def test_video_analytics_and_scope_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.studio.publisher import ANALYTICS_SCOPE, StudioYouTube

    mode = {"scope": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "tok"})
        if mode["scope"]:
            return httpx.Response(
                403, json={"error": {"message": "Request had insufficient authentication scopes."}}
            )
        if request.url.params.get("dimensions") == "elapsedVideoTimeRatio":
            return httpx.Response(200, json={"rows": [[0.01, 1.0], [0.5, 0.6], [1.0, 0.4]]})
        return httpx.Response(200, json={"rows": [[120, 7, 1, 71.5, 39.0]]})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    yt = StudioYouTube("c", "s", "r")
    stats, curve = await yt.video_analytics("v1", "2026-11-01", "2026-11-10")
    assert stats["views"] == 120 and stats["averageViewPercentage"] == 71.5
    assert curve == [(0.01, 1.0), (0.5, 0.6), (1.0, 0.4)]
    mode["scope"] = True
    with pytest.raises(YouTubePublishError, match=ANALYTICS_SCOPE.replace(".", r"\.")):
        await yt.video_analytics("v1", "2026-11-01", "2026-11-10")
