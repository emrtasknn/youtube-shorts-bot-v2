import httpx
import pytest

from app.infrastructure.providers.contracts import (
    ProviderCapability,
    ProviderRequest,
)
from app.infrastructure.providers.wikimedia_commons import WikimediaCommonsProvider


def _request() -> ProviderRequest:
    return ProviderRequest(
        request_id="req-commons-1",
        run_id="run-commons-1",
        capability=ProviderCapability.STOCK_MEDIA,
        operation="search_photos",
        provider="wikimedia_commons",
        payload={"query": "Chernobyl Reactor 4 1986 archival photograph", "per_page": 2},
    )


@pytest.mark.asyncio
async def test_search_photos_normalizes_commons_metadata_and_license() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"].startswith("YouTubeShortsBotV2/")
        assert request.url.params["gsrnamespace"] == "6"
        assert "Chernobyl Reactor 4" in request.url.params["gsrsearch"]
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "pageid": 42,
                            "title": "File:Chernobyl Reactor 4.jpg",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/full.jpg",
                                    "thumburl": "https://upload.wikimedia.org/thumb.jpg",
                                    "width": 2400,
                                    "height": 1600,
                                    "thumbwidth": 1800,
                                    "thumbheight": 1200,
                                    "mime": "image/jpeg",
                                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Chernobyl_Reactor_4.jpg",
                                    "extmetadata": {
                                        "ImageDescription": {"value": "Reactor 4 at Chernobyl"},
                                        "Artist": {"value": "Example photographer"},
                                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                        "LicenseUrl": {
                                            "value": "https://creativecommons.org/licenses/by-sa/4.0/"
                                        },
                                    },
                                }
                            ],
                        }
                    ]
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = WikimediaCommonsProvider(client=client)
    try:
        result = await provider.execute(_request())
    finally:
        await client.aclose()

    item = result.output["items"][0]
    assert result.provider == "wikimedia_commons"
    assert item["id"] == "commons:42"
    assert item["download_url"].endswith("thumb.jpg")
    assert item["source_url"].startswith("https://commons.wikimedia.org/")
    assert item["license"] == "CC BY-SA 4.0"
    assert item["license_url"].startswith("https://creativecommons.org/")
    assert item["portrait_crop_allowed"] is True


@pytest.mark.asyncio
async def test_search_rejects_empty_query() -> None:
    request = _request()
    invalid = ProviderRequest(
        request_id=request.request_id,
        run_id=request.run_id,
        capability=request.capability,
        operation=request.operation,
        provider=request.provider,
        payload={"query": "  "},
    )
    provider = WikimediaCommonsProvider()
    with pytest.raises(Exception, match="non-empty query"):
        await provider.execute(invalid)
