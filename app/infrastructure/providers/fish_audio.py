from __future__ import annotations

from typing import Any

import httpx

from app.infrastructure.providers.contracts import (
    ErrorCategory,
    ProviderCapability,
    ProviderError,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
)


class FishAudioTTSProvider:
    name = "fish_audio"
    capabilities = frozenset({ProviderCapability.TTS})

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.fish.audio",
        model: str = "s2.1-pro-free",
        format: str = "mp3",
        reference_id: str | None = None,
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Fish Audio API key must not be empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._format = format
        self._reference_id = reference_id
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        if request.operation != "text_to_speech":
            raise ProviderError(
                code="UNSUPPORTED_OPERATION",
                category=ErrorCategory.INVALID_REQUEST,
                provider=self.name,
                message=f"Unsupported Fish Audio operation: {request.operation}",
            )

        text = str(request.payload.get("text", "")).strip()
        if not text:
            raise ProviderError(
                code="MISSING_TEXT",
                category=ErrorCategory.INVALID_REQUEST,
                provider=self.name,
                message="Fish Audio TTS requires non-empty text",
            )

        model = str(request.model or request.payload.get("model") or self._model)
        audio_format = str(request.payload.get("format") or self._format)
        payload: dict[str, Any] = {
            "text": text,
            "format": audio_format,
        }
        reference_id = request.payload.get("reference_id") or self._reference_id
        if reference_id:
            payload["reference_id"] = str(reference_id)

        audio = await self._request(model, payload, request.timeout_seconds)
        input_units = len(text.encode("utf-8"))
        return ProviderResult(
            success=True,
            provider=self.name,
            request_id=request.request_id,
            output={
                "audio_bytes": audio,
                "format": audio_format,
                "mime_type": self._mime_type(audio_format),
                "model": model,
            },
            usage=ProviderUsage(
                input_units=input_units,
                output_units=len(audio),
                total_units=input_units,
            ),
            metadata={
                "source": "fish_audio",
                "model": model,
                "format": audio_format,
            },
        )

    async def _request(
        self,
        model: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> bytes:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "model": model,
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=timeout_seconds or self._timeout_seconds
        )
        try:
            response = await client.post(
                f"{self._base_url}/v1/tts",
                headers=headers,
                json=payload,
                timeout=timeout_seconds or self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                code="TIMEOUT",
                category=ErrorCategory.TIMEOUT,
                provider=self.name,
                message="Fish Audio request timed out",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                code="NETWORK_ERROR",
                category=ErrorCategory.TRANSIENT,
                provider=self.name,
                message="Fish Audio request failed before receiving a response",
                retryable=True,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if 200 <= response.status_code < 300:
            if not response.content:
                raise ProviderError(
                    code="EMPTY_AUDIO",
                    category=ErrorCategory.QUALITY,
                    provider=self.name,
                    message="Fish Audio returned an empty audio response",
                )
            return response.content

        raise self._provider_error(response)

    def _provider_error(self, response: httpx.Response) -> ProviderError:
        retry_after = response.headers.get("Retry-After")
        retry_after_seconds = float(retry_after) if retry_after else None

        if response.status_code in {401, 403}:
            category = ErrorCategory.AUTHENTICATION
            retryable = False
        elif response.status_code == 429:
            category = ErrorCategory.RATE_LIMITED
            retryable = True
        elif response.status_code in {402, 413}:
            category = ErrorCategory.QUOTA_EXHAUSTED
            retryable = False
        elif 500 <= response.status_code <= 599:
            category = ErrorCategory.TRANSIENT
            retryable = True
        elif response.status_code == 404:
            category = ErrorCategory.NOT_FOUND
            retryable = False
        else:
            category = ErrorCategory.INVALID_REQUEST
            retryable = False

        return ProviderError(
            code=f"HTTP_{response.status_code}",
            category=category,
            provider=self.name,
            message=f"Fish Audio API returned HTTP {response.status_code}",
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
            status_code=response.status_code,
        )

    @staticmethod
    def _mime_type(audio_format: str) -> str:
        return {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "opus": "audio/opus",
        }.get(audio_format.lower(), "application/octet-stream")
