from dataclasses import replace

import httpx
import pytest

from app.infrastructure.providers.contracts import (
    ErrorCategory,
    ProviderCapability,
    ProviderError,
    ProviderRequest,
)
from app.infrastructure.providers.gemini import GeminiTextProvider


def request() -> ProviderRequest:
    return ProviderRequest(
        request_id="req-1",
        run_id="run-1",
        capability=ProviderCapability.TEXT_GENERATION,
        operation="generate_text",
        provider="gemini",
        payload={
            "prompt": "Write a short history hook.",
            "system_instruction": "You write concise Turkish Shorts scripts.",
            "generation_config": {"temperature": 0.7, "maxOutputTokens": 200},
        },
    )


@pytest.mark.asyncio
async def test_generate_text_normalizes_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "secret"
        assert request.url.path.endswith("/models/gemini-test:generateContent")
        payload = request.read()
        assert b"Write a short history hook." in payload
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "İnanılmaz bir tarih hikâyesi..."}],
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 20,
                    "totalTokenCount": 30,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeminiTextProvider("secret", model="gemini-default", client=client)
    try:
        result = await provider.execute(replace(request(), model="gemini-test"))
    finally:
        await client.aclose()

    assert result.success is True
    assert result.provider == "gemini"
    assert result.output["text"].startswith("İnanılmaz")
    assert result.usage.total_units == 30


@pytest.mark.asyncio
async def test_rate_limit_preserves_retry_after() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "9"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeminiTextProvider("secret", client=client)
    try:
        with pytest.raises(ProviderError) as exc_info:
            await provider.execute(request())
    finally:
        await client.aclose()

    assert exc_info.value.category == ErrorCategory.RATE_LIMITED
    assert exc_info.value.retryable is True
    assert exc_info.value.retry_after_seconds == 9


@pytest.mark.asyncio
async def test_empty_candidate_is_quality_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeminiTextProvider("secret", client=client)
    try:
        with pytest.raises(ProviderError) as exc_info:
            await provider.execute(request())
    finally:
        await client.aclose()

    assert exc_info.value.category == ErrorCategory.QUALITY
    assert exc_info.value.retryable is False
