import httpx
import pytest

from app.config.settings import Settings
from app.infrastructure.providers.contracts import (
    ErrorCategory,
    ProviderCapability,
    ProviderError,
    ProviderRequest,
)
from app.infrastructure.providers.factory import build_provider_registry
from app.infrastructure.providers.pexels import PexelsStockMediaProvider


def request(operation: str = "search_photos") -> ProviderRequest:
    return ProviderRequest(
        request_id="req-1",
        run_id="run-1",
        capability=ProviderCapability.STOCK_MEDIA,
        operation=operation,
        provider="pexels",
        payload={"query": "ancient roman ruins", "per_page": 2, "orientation": "portrait"},
    )


@pytest.mark.asyncio
async def test_search_photos_normalizes_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "secret"
        assert request.url.path == "/v1/search"
        assert request.url.params["query"] == "ancient roman ruins"
        assert request.url.params["per_page"] == "2"
        return httpx.Response(
            200,
            json={
                "page": 1,
                "per_page": 2,
                "total_results": 2,
                "photos": [
                    {
                        "id": 123,
                        "width": 1000,
                        "height": 1500,
                        "url": "https://pexels.com/photo/123",
                        "photographer": "Test",
                        "photographer_url": "https://pexels.com/test",
                        "alt": "Roman ruins",
                        "src": {
                            "original": "https://images.example/original.jpg",
                            "large": "https://images.example/large.jpg",
                            "portrait": "https://images.example/portrait.jpg",
                        },
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = PexelsStockMediaProvider("secret", client=client)
    try:
        result = await provider.execute(request())
    finally:
        await client.aclose()

    assert result.success is True
    assert result.provider == "pexels"
    assert result.output["total_results"] == 2
    assert result.output["items"][0]["download_url"].endswith("portrait.jpg")


@pytest.mark.asyncio
async def test_rate_limit_preserves_retry_after() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "12"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = PexelsStockMediaProvider("secret", client=client)
    try:
        with pytest.raises(ProviderError) as exc_info:
            await provider.execute(request())
    finally:
        await client.aclose()

    assert exc_info.value.category == ErrorCategory.RATE_LIMITED
    assert exc_info.value.retryable is True
    assert exc_info.value.retry_after_seconds == 12


@pytest.mark.asyncio
async def test_auth_failure_is_not_retryable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = PexelsStockMediaProvider("secret", client=client)
    try:
        with pytest.raises(ProviderError) as exc_info:
            await provider.execute(request())
    finally:
        await client.aclose()

    assert exc_info.value.category == ErrorCategory.AUTHENTICATION
    assert exc_info.value.retryable is False


def test_factory_does_not_register_without_credentials() -> None:
    registry = build_provider_registry(Settings(pexels_api_key=""))
    assert registry.candidates(ProviderCapability.STOCK_MEDIA) == []
