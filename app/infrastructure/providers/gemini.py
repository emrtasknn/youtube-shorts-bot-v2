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


class GeminiTextProvider:
    name = "gemini"
    capabilities = frozenset({ProviderCapability.TEXT_GENERATION})

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        model: str = "gemini-3.6-flash",
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Gemini API key must not be empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        if request.operation != "generate_text":
            raise ProviderError(
                code="UNSUPPORTED_OPERATION",
                category=ErrorCategory.INVALID_REQUEST,
                provider=self.name,
                message=f"Unsupported Gemini operation: {request.operation}",
            )

        prompt = str(request.payload.get("prompt", "")).strip()
        if not prompt:
            raise ProviderError(
                code="MISSING_PROMPT",
                category=ErrorCategory.INVALID_REQUEST,
                provider=self.name,
                message="Gemini text generation requires a non-empty prompt",
            )

        model = str(request.model or request.payload.get("model") or self._model)
        payload = self._build_payload(request.payload, prompt)
        response = await self._request(model, payload, request.timeout_seconds)
        text, usage = self._normalize_response(response)

        return ProviderResult(
            success=True,
            provider=self.name,
            request_id=request.request_id,
            output={"text": text, "model": model},
            usage=usage,
            metadata={"source": "gemini"},
        )

    async def _request(
        self,
        model: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=timeout_seconds or self._timeout_seconds)
        try:
            response = await client.post(
                f"{self._base_url}/models/{model}:generateContent",
                headers=headers,
                json=payload,
                timeout=timeout_seconds or self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                code="TIMEOUT",
                category=ErrorCategory.TIMEOUT,
                provider=self.name,
                message="Gemini request timed out",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                code="NETWORK_ERROR",
                category=ErrorCategory.TRANSIENT,
                provider=self.name,
                message="Gemini request failed before receiving a response",
                retryable=True,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if 200 <= response.status_code < 300:
            data = response.json()
            if not isinstance(data, dict):
                raise ProviderError(
                    code="INVALID_RESPONSE",
                    category=ErrorCategory.INVALID_REQUEST,
                    provider=self.name,
                    message="Gemini API returned a non-object JSON response",
                )
            return data

        raise self._provider_error(response)

    @staticmethod
    def _build_payload(payload: dict[str, Any], prompt: str) -> dict[str, Any]:
        request_payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
        }
        system_instruction = payload.get("system_instruction")
        if system_instruction:
            request_payload["system_instruction"] = {"parts": [{"text": str(system_instruction)}]}
        generation_config = payload.get("generation_config")
        if isinstance(generation_config, dict) and generation_config:
            request_payload["generationConfig"] = generation_config
        return request_payload

    def _normalize_response(
        self, response: dict[str, Any]
    ) -> tuple[str, ProviderUsage]:
        candidates = response.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ProviderError(
                code="NO_CANDIDATE",
                category=ErrorCategory.QUALITY,
                provider=self.name,
                message="Gemini returned no candidate content",
            )

        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [
            str(part["text"])
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        text = "".join(texts).strip()
        if not text:
            raise ProviderError(
                code="EMPTY_OUTPUT",
                category=ErrorCategory.QUALITY,
                provider=self.name,
                message="Gemini returned empty text content",
            )

        usage_metadata = response.get("usageMetadata", {})
        if not isinstance(usage_metadata, dict):
            usage_metadata = {}
        input_units = self._as_int(usage_metadata.get("promptTokenCount"))
        output_units = self._as_int(usage_metadata.get("candidatesTokenCount"))
        total_units = self._as_int(usage_metadata.get("totalTokenCount"))
        return text, ProviderUsage(
            input_units=input_units,
            output_units=output_units,
            total_units=total_units,
        )

    def _provider_error(self, response: httpx.Response) -> ProviderError:
        retry_after = response.headers.get("Retry-After")
        retry_after_seconds = float(retry_after) if retry_after else None

        if response.status_code in {401, 403}:
            category = ErrorCategory.AUTHENTICATION
            retryable = False
        elif response.status_code == 429:
            category = ErrorCategory.RATE_LIMITED
            retryable = True
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
            message=f"Gemini API returned HTTP {response.status_code}",
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
            status_code=response.status_code,
        )

    @staticmethod
    def _as_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
