from dataclasses import replace

import httpx
import pytest

from app.infrastructure.providers.contracts import (
    ErrorCategory,
    ProviderCapability,
    ProviderError,
    ProviderRequest,
)
from app.infrastructure.providers.fish_audio import FishAudioTTSProvider


def request() -> ProviderRequest:
    return ProviderRequest(
        request_id="req-tts-1",
        run_id="run-1",
        capability=ProviderCapability.TTS,
        operation="text_to_speech",
        provider="fish_audio",
        payload={"text": "Merhaba, bugün tarihte ne oldu?", "format": "mp3"},
    )


@pytest.mark.asyncio
async def test_tts_returns_audio_bytes() -> None:
    audio = b"fake-mp3-audio"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        assert request.headers["model"] == "s2.1-pro-free"
        assert request.url.path == "/v1/tts"
        assert b"Merhaba" in request.read()
        return httpx.Response(200, content=audio)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FishAudioTTSProvider("secret", client=client)
    try:
        result = await provider.execute(request())
    finally:
        await client.aclose()

    assert result.success is True
    assert result.provider == "fish_audio"
    assert result.output["audio_bytes"] == audio
    assert result.output["mime_type"] == "audio/mpeg"
    assert result.usage.input_units == len("Merhaba, bugün tarihte ne oldu?".encode("utf-8"))


@pytest.mark.asyncio
async def test_rate_limit_preserves_retry_after() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "11"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FishAudioTTSProvider("secret", client=client)
    try:
        with pytest.raises(ProviderError) as exc_info:
            await provider.execute(request())
    finally:
        await client.aclose()

    assert exc_info.value.category == ErrorCategory.RATE_LIMITED
    assert exc_info.value.retryable is True
    assert exc_info.value.retry_after_seconds == 11


@pytest.mark.asyncio
async def test_quota_failure_is_not_retryable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(402)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FishAudioTTSProvider("secret", client=client)
    try:
        with pytest.raises(ProviderError) as exc_info:
            await provider.execute(request())
    finally:
        await client.aclose()

    assert exc_info.value.category == ErrorCategory.QUOTA_EXHAUSTED
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_reference_id_can_be_overridden() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert b"voice-123" in request.read()
        return httpx.Response(200, content=b"audio")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FishAudioTTSProvider("secret", reference_id="default", client=client)
    try:
        result = await provider.execute(
            replace(
                request(),
                payload={
                    "text": "Ses testi",
                    "reference_id": "voice-123",
                },
            )
        )
    finally:
        await client.aclose()

    assert result.output["audio_bytes"] == b"audio"
