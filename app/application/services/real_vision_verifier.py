from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.application.services.visual_semantic_verification import (
    VisualSemanticScore,
    VisualVerificationPolicy,
    VisualVerificationResult,
)
from app.application.services.visual_semantic_verifier import (
    DeterministicVisualSemanticVerifier,
    VisualSemanticVerifier,
    VisualVerificationContext,
)
from app.infrastructure.providers.contracts import (
    ErrorCategory,
    ProviderError,
)


@dataclass(frozen=True, slots=True)
class VisionVerificationConfig:
    api_key: str
    model: str = "gemini-3.8-flash"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    timeout_seconds: float = 45.0
    max_image_bytes: int = 6_000_000


class GeminiVisionSemanticVerifier:
    """Pixel-level semantic verifier backed by Gemini multimodal input."""

    name = "gemini-vision-v1"

    def __init__(
        self,
        config: VisionVerificationConfig,
        *,
        policy: VisualVerificationPolicy | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not config.api_key.strip():
            raise ValueError("Gemini vision API key must not be empty")
        self._config = config
        self._policy = policy or VisualVerificationPolicy()
        self._client = client

    def verify(
        self,
        item: dict[str, Any],
        *,
        context: VisualVerificationContext,
    ) -> VisualVerificationResult:
        image_url = str(item.get("download_url") or item.get("url") or "").strip()
        if not image_url:
            raise ProviderError(
                code="MISSING_IMAGE_URL",
                category=ErrorCategory.INVALID_REQUEST,
                provider=self.name,
                message="Vision verification requires an image URL",
            )

        image_bytes, mime_type = self._download_image(image_url)
        response = self._analyze(image_bytes, mime_type, context)
        score = self._score_response(response, context)
        decision = self._policy.decide(score)
        matched = tuple(str(value) for value in response.get("matched_signals", []) if value)
        missing = tuple(str(value) for value in response.get("missing_signals", []) if value)
        violated = tuple(str(value) for value in response.get("violated_constraints", []) if value)
        return VisualVerificationResult(
            decision=decision,
            score=score,
            verifier=self.name,
            matched_signals=matched,
            missing_signals=missing,
            violated_constraints=violated,
        )

    def _download_image(self, url: str) -> tuple[bytes, str]:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=self._config.timeout_seconds)
        try:
            response = client.get(url)
            response.raise_for_status()
            content = response.content
            if len(content) > self._config.max_image_bytes:
                raise ProviderError(
                    code="IMAGE_TOO_LARGE",
                    category=ErrorCategory.QUALITY,
                    provider=self.name,
                    message="Image exceeds vision verification size budget",
                )
            content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
            if not content_type.startswith("image/"):
                content_type = "image/jpeg"
            return content, content_type
        except httpx.TimeoutException as exc:
            raise ProviderError(
                code="IMAGE_TIMEOUT",
                category=ErrorCategory.TIMEOUT,
                provider=self.name,
                message="Image download timed out",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                code="IMAGE_DOWNLOAD_ERROR",
                category=ErrorCategory.TRANSIENT,
                provider=self.name,
                message="Image download failed",
                retryable=True,
            ) from exc
        finally:
            if owns_client:
                client.close()

    def _analyze(
        self,
        image_bytes: bytes,
        mime_type: str,
        context: VisualVerificationContext,
    ) -> dict[str, Any]:
        prompt = self._build_prompt(context)
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0,
                "maxOutputTokens": 800,
            },
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._config.api_key,
        }
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=self._config.timeout_seconds)
        try:
            response = client.post(
                f"{self._config.base_url.rstrip('/')}/models/{self._config.model}:generateContent",
                headers=headers,
                json=payload,
            )
            if not 200 <= response.status_code < 300:
                raise ProviderError(
                    code=f"HTTP_{response.status_code}",
                    category=(
                        ErrorCategory.RATE_LIMITED
                        if response.status_code == 429
                        else ErrorCategory.TRANSIENT
                        if response.status_code >= 500
                        else ErrorCategory.INVALID_REQUEST
                    ),
                    provider=self.name,
                    message=f"Gemini vision API returned HTTP {response.status_code}",
                    retryable=response.status_code == 429 or response.status_code >= 500,
                    status_code=response.status_code,
                )
            data = response.json()
            text = self._extract_text(data)
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("Vision response must be a JSON object")
            return parsed
        except httpx.TimeoutException as exc:
            raise ProviderError(
                code="VISION_TIMEOUT",
                category=ErrorCategory.TIMEOUT,
                provider=self.name,
                message="Gemini vision request timed out",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                code="VISION_NETWORK_ERROR",
                category=ErrorCategory.TRANSIENT,
                provider=self.name,
                message="Gemini vision request failed",
                retryable=True,
            ) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise ProviderError(
                code="INVALID_VISION_OUTPUT",
                category=ErrorCategory.QUALITY,
                provider=self.name,
                message="Gemini vision returned invalid JSON",
            ) from exc
        finally:
            if owns_client:
                client.close()

    @staticmethod
    def _build_prompt(context: VisualVerificationContext) -> str:
        return (
            "Inspect the actual image pixels, not metadata. Determine whether the image "
            "visually depicts the requested subject and action. Return JSON only with: "
            "entity_match, action_match, context_match, must_show_match, "
            "must_avoid_compliance, confidence, matched_signals, missing_signals, "
            "violated_constraints. Each score is 0 to 1. confidence is your confidence "
            "in the visual judgment. Do not infer an object merely because it could be "
            "present; require visible evidence. "
            f"Entities: {list(context.entities)}. Location: {context.location}. "
            f"Era: {context.era}. Action: {context.action}. "
            f"Must show: {list(context.must_show)}. Must avoid: {list(context.must_avoid)}."
        )

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("No Gemini vision candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(
            str(part["text"])
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ).strip()
        if not text:
            raise ValueError("Empty Gemini vision response")
        return text

    @staticmethod
    def _score_response(
        response: dict[str, Any],
        context: VisualVerificationContext,
    ) -> VisualSemanticScore:
        def score(name: str) -> float:
            try:
                return max(0.0, min(1.0, float(response.get(name, 0.0))))
            except (TypeError, ValueError):
                return 0.0

        # Confidence calibrates the model's raw judgment conservatively.
        confidence = max(0.0, min(1.0, float(response.get("confidence", 0.0))))
        entity = score("entity_match")
        action = score("action_match")
        context_match = score("context_match")
        must_show = score("must_show_match")
        avoid = score("must_avoid_compliance")
        overall = (
            entity * 0.30 + action * 0.15 + context_match * 0.20 + must_show * 0.25 + avoid * 0.10
        ) * (0.70 + 0.30 * confidence)
        return VisualSemanticScore(
            entity_match=entity,
            action_match=action,
            context_match=context_match,
            must_show_match=must_show,
            must_avoid_compliance=avoid,
            overall=overall,
        )


class CostAwareVisionVerifier:
    """Runs real vision on a bounded shortlist and fails over safely."""

    def __init__(
        self,
        primary: VisualSemanticVerifier,
        fallback: VisualSemanticVerifier | None = None,
        *,
        max_verified_candidates: int = 6,
    ) -> None:
        if max_verified_candidates < 1:
            raise ValueError("max_verified_candidates must be positive")
        self.primary = primary
        self.fallback = fallback or DeterministicVisualSemanticVerifier()
        self.max_verified_candidates = max_verified_candidates
        self.name = f"{getattr(primary, 'name', 'vision')}+cost-aware"

    def verify(
        self,
        item: dict[str, Any],
        *,
        context: VisualVerificationContext,
    ) -> VisualVerificationResult:
        try:
            return self.primary.verify(item, context=context)
        except Exception:
            result = self.fallback.verify(item, context=context)
            return VisualVerificationResult(
                decision=result.decision,
                score=result.score,
                verifier=f"failover:{result.verifier}",
                matched_signals=result.matched_signals,
                missing_signals=result.missing_signals,
                violated_constraints=result.violated_constraints,
            )
