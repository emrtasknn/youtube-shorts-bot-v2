"""Minimal JSON-mode LLM clients (Groq OpenAI-compatible API and Gemini REST).

Studio only needs "prompt in, JSON out". Keeping it to plain httpx calls avoids
the reliability/idempotency stack of the legacy pipeline for this path.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

import httpx


class LLMError(RuntimeError):
    pass


class JsonLLM(Protocol):
    async def complete_json(self, system: str, user: str) -> dict[str, Any]: ...


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LLMError("Model JSON döndürmedi")
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model bozuk JSON döndürdü: {exc}") from exc
    if not isinstance(value, dict):
        raise LLMError("Model JSON nesnesi döndürmedi")
    return value


class GroqLLM:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "openai/gpt-oss-20b",
        base_url: str = "https://api.groq.com/openai/v1",
        timeout: float = 90.0,
    ) -> None:
        if not api_key:
            raise LLMError("GROQ_API_KEY gerekli")
        self._key, self._model, self._url, self._timeout = api_key, model, base_url, timeout

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(
                f"{self._url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self._key}"},
                json=body,
            )

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._model,
            "temperature": 0.8,
            "max_completion_tokens": 8192,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if "gpt-oss" in self._model:
            # reasoning models spend the token budget thinking first; keep that short
            # so the script itself fits in the answer
            body["reasoning_effort"] = "low"
        r = await self._post(body)
        if r.status_code == 400 and "json_validate_failed" in r.text:
            # Groq's strict JSON mode sometimes rejects an empty/partial generation;
            # ask again without it and pull the JSON object out of the text.
            body.pop("response_format")
            r = await self._post(body)
        if r.status_code >= 400:
            raise LLMError(f"Groq HTTP {r.status_code}: {r.text[:300]}")
        choice = r.json()["choices"][0]
        content = str(choice.get("message", {}).get("content") or "")
        try:
            return parse_json_object(content)
        except LLMError as exc:
            reason = choice.get("finish_reason", "?")
            raise LLMError(f"{exc} (finish_reason={reason}, {len(content)} karakter)") from exc


class GeminiLLM:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-2.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 90.0,
    ) -> None:
        if not api_key:
            raise LLMError("GEMINI_API_KEY gerekli")
        self._key, self._model, self._url, self._timeout = api_key, model, base_url, timeout

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._url.rstrip('/')}/models/{self._model}:generateContent",
                params={"key": self._key},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {
                        "temperature": 0.8,
                        "responseMimeType": "application/json",
                    },
                },
            )
        if r.status_code >= 400:
            raise LLMError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Gemini boş yanıt: {str(data)[:300]}") from exc
        return parse_json_object(str(text))


class FallbackLLM:
    """Try providers in order; the first one that answers wins."""

    def __init__(self, providers: list[JsonLLM]) -> None:
        if not providers:
            raise LLMError("Hiç LLM sağlayıcısı yapılandırılmamış (GROQ_API_KEY / GEMINI_API_KEY)")
        self._providers = providers

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        errors: list[str] = []
        for p in self._providers:
            try:
                return await p.complete_json(system, user)
            except (LLMError, httpx.HTTPError, KeyError) as exc:
                errors.append(f"{type(p).__name__}: {exc}")
        raise LLMError(" | ".join(errors))
