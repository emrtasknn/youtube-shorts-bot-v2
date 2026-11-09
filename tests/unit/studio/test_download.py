import httpx
import pytest

from app.studio.http import USER_AGENT
from app.studio.render.pipeline import VisualFetchError, download_image, original_of_thumb

THUMB = (
    "https://thumb.wikimedia.org/wikipedia/commons/thumb/4/4b/"
    "Victory_Monument_in_Ulus_Square%2C_1st_Turkish_Grand_National_Assembly%2C_1930%27s_"
    "%2817075286852%29.jpg/1920px-Victory_Monument_in_Ulus_Square%2C_1st_Turkish_Grand_"
    "National_Assembly%2C_1930%27s_%2817075286852%29.jpg?utm_source=commons.wikimedia.org"
)
ORIGINAL = (
    "https://upload.wikimedia.org/wikipedia/commons/4/4b/"
    "Victory_Monument_in_Ulus_Square%2C_1st_Turkish_Grand_National_Assembly%2C_1930%27s_"
    "%2817075286852%29.jpg"
)


def test_user_agent_names_the_tool_and_a_contact() -> None:
    assert USER_AGENT.startswith("BirGaripTarihStudio/")
    assert "https://github.com/emrtasknn/youtube-shorts-bot-v2" in USER_AGENT
    assert "httpx/" in USER_AGENT


def test_original_of_thumb() -> None:
    assert original_of_thumb(THUMB) == ORIGINAL
    assert original_of_thumb(ORIGINAL) is None
    assert original_of_thumb("https://example.com/a.jpg") is None


def _transport(replies: dict[str, list[httpx.Response]], seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        key = str(request.url).split("?", 1)[0]
        queue = replies.get(key) or [httpx.Response(404)]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_sends_user_agent_and_drops_tracking_query() -> None:
    seen: list[httpx.Request] = []
    thumb = THUMB.split("?", 1)[0]
    data = await download_image(
        THUMB, transport=_transport({thumb: [httpx.Response(200, content=b"img")]}, seen), pause=0
    )
    assert data == b"img"
    assert seen[0].headers["user-agent"] == USER_AGENT
    assert "utm_source" not in str(seen[0].url)


@pytest.mark.asyncio
async def test_blocked_thumbnail_falls_back_to_original() -> None:
    seen: list[httpx.Request] = []
    thumb = THUMB.split("?", 1)[0]
    replies = {
        thumb: [httpx.Response(403)],
        ORIGINAL: [httpx.Response(200, content=b"original")],
    }
    assert await download_image(THUMB, transport=_transport(replies, seen), pause=0) == b"original"
    assert [str(r.url).split("?")[0] for r in seen] == [thumb, thumb, ORIGINAL]


@pytest.mark.asyncio
async def test_throttled_request_is_retried_once() -> None:
    seen: list[httpx.Request] = []
    url = "https://example.com/a.jpg"
    replies = {
        url: [httpx.Response(429, headers={"retry-after": "0"}), httpx.Response(200, content=b"ok")]
    }
    assert await download_image(url, transport=_transport(replies, seen), pause=0) == b"ok"
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_gives_up_with_a_clear_error() -> None:
    seen: list[httpx.Request] = []

    def always_blocked(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(403)

    with pytest.raises(VisualFetchError, match="HTTP 403"):
        await download_image(THUMB, transport=httpx.MockTransport(always_blocked), pause=0)
    assert len(seen) == 4  # thumbnail twice, original twice
