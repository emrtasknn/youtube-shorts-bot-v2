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


class GroqTextProvider:
    name = "groq"
    capabilities = frozenset({ProviderCapability.TEXT_GENERATION})

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "openai/gpt-oss-20b",
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Groq API key must not be empty")
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
                message=f"Unsupported Groq operation: {request.operation}",
            )

        prompt = str(request.payload.get("prompt", "")).strip()
        if not prompt:
            raise ProviderError(
                code="MISSING_PROMPT",
                category=ErrorCategory.INVALID_REQUEST,
                provider=self.name,
                message="Groq text generation requires a non-empty prompt",
            )

        model = str(request.model or request.payload.get("model") or self._model)
        payload = self._build_payload(request.payload, prompt, model)
        response = await self._request(payload, request.timeout_seconds)
        text, usage, metadata = self._normalize_response(response)

        return ProviderResult(
            success=True,
            provider=self.name,
            request_id=request.request_id,
            output={"text": text, "model": model},
            usage=usage,
            metadata=metadata,
        )

    async def _request(
        self,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=timeout_seconds or self._timeout_seconds)
        try:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout_seconds or self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                code="TIMEOUT",
                category=ErrorCategory.TIMEOUT,
                provider=self.name,
                message="Groq request timed out",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                code="NETWORK_ERROR",
                category=ErrorCategory.TRANSIENT,
                provider=self.name,
                message="Groq request failed before receiving a response",
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
                    message="Groq API returned a non-object JSON response",
                )
            return data

        raise self._provider_error(response)

    @staticmethod
    def _build_payload(
        payload: dict[str, Any],
        prompt: str,
        model: str,
    ) -> dict[str, Any]:
        system_instruction = payload.get("system_instruction")
        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": str(system_instruction)})
        messages.append({"role": "user", "content": prompt})

        request_payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "include_reasoning": False,
        }
        generation_config = payload.get("generation_config")
        if isinstance(generation_config, dict):
            max_tokens = generation_config.get("maxOutputTokens")
            if max_tokens is not None:
                request_payload["max_completion_tokens"] = int(max_tokens)
        return request_payload

    def _normalize_response(
        self,
        response: dict[str, Any],
    ) -> tuple[str, ProviderUsage, dict[str, Any]]:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(
                code="NO_CHOICE",
                category=ErrorCategory.QUALITY,
                provider=self.name,
                message="Groq returned no completion choice",
            )

        choice = choices[0]
        if not isinstance(choice, dict):
            raise ProviderError(
                code="INVALID_RESPONSE",
                category=ErrorCategory.QUALITY,
                provider=self.name,
                message="Groq returned an invalid completion choice",
            )
        message = choice.get("message", {})
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ProviderError(
                code="EMPTY_OUTPUT",
                category=ErrorCategory.QUALITY,
                provider=self.name,
                message="Groq returned empty text content",
            )

        usage = response.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        input_units = self._as_int(usage.get("prompt_tokens"))
        output_units = self._as_int(usage.get("completion_tokens"))
        total_units = self._as_int(usage.get("total_tokens"))
        metadata = {
            "source": "groq",
            "finish_reason": choice.get("finish_reason"),
        }
        return (
            text.strip(),
            ProviderUsage(
                input_units=input_units,
                output_units=output_units,
                total_units=total_units,
            ),
            metadata,
        )

    def _provider_error(self, response: httpx.Response) -> ProviderError:
        # Preserve Groq's actionable validation detail without exposing the API key.
        try:
            error_body = response.json()
            detail = (
                error_body.get("error", {}).get("message") if isinstance(error_body, dict) else None
            )
        except ValueError:
            detail = None
        message = f"Groq API returned HTTP {response.status_code}"
        if isinstance(detail, str) and detail.strip():
            message = f"{message}: {detail.strip()}"
        retry_after = response.headers.get("retry-after")
        retry_after_seconds = None
        if retry_after:
            try:
                retry_after_seconds = float(retry_after)
            except ValueError:
                retry_after_seconds = None

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
            message=message,
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
