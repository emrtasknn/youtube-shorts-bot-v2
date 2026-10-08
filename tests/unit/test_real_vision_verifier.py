from __future__ import annotations

from app.application.services.real_vision_verifier import (
    CostAwareVisionVerifier,
    GeminiVisionSemanticVerifier,
    VisionVerificationConfig,
)
from app.application.services.visual_semantic_verification import VisualVerificationDecision
from app.application.services.visual_semantic_verifier import (
    DeterministicVisualSemanticVerifier,
    VisualVerificationContext,
)


class FakeResponse:
    status_code = 200
    headers = {"content-type": "image/jpeg"}

    def __init__(self, payload):
        self._payload = payload
        self.content = b"fake-image-bytes"

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self):
        self.posts = []

    def get(self, url):
        return FakeResponse({})

    def post(self, url, headers=None, json_payload=None, **kwargs):
        payload = kwargs.get("json", json_payload)
        self.posts.append((url, headers, payload))
        return FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": __import__("json").dumps(
                                        {
                                            "entity_match": 1.0,
                                            "action_match": 0.9,
                                            "context_match": 1.0,
                                            "must_show_match": 1.0,
                                            "must_avoid_compliance": 1.0,
                                            "confidence": 0.95,
                                            "matched_signals": ["roman emperor", "standing"],
                                            "missing_signals": [],
                                            "violated_constraints": [],
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        )

    def close(self):
        return None


def _context() -> VisualVerificationContext:
    return VisualVerificationContext(
        entities=("Roman emperor",),
        location="Rome",
        era="ancient Rome",
        action="standing",
        must_show=("Roman emperor",),
        must_avoid=("modern clothing",),
    )


def test_gemini_vision_verifier_uses_actual_image_bytes_and_returns_accept() -> None:
    client = FakeClient()
    verifier = GeminiVisionSemanticVerifier(
        VisionVerificationConfig(api_key="test-key"),
        client=client,
    )

    result = verifier.verify(
        {"download_url": "https://example.test/image.jpg"},
        context=_context(),
    )

    assert result.verifier == "gemini-vision-v1"
    assert result.decision == VisualVerificationDecision.ACCEPT
    assert result.score.overall > 0.78
    assert len(client.posts) == 1
    parts = client.posts[0][2]["contents"][0]["parts"]
    assert "inline_data" in parts[1]
    assert parts[1]["inline_data"]["data"]


def test_cost_aware_vision_verifier_falls_back_when_real_vision_fails() -> None:
    class BrokenVision:
        name = "gemini-vision-v1"

        def verify(self, item, *, context):
            raise RuntimeError("vision unavailable")

    result = CostAwareVisionVerifier(
        BrokenVision(),
        fallback=DeterministicVisualSemanticVerifier(),
    ).verify(
        {"title": "Roman emperor standing in Rome"},
        context=_context(),
    )

    assert result.verifier.startswith("failover:")
    assert result.decision in {
        VisualVerificationDecision.ACCEPT,
        VisualVerificationDecision.ACCEPT_DEGRADED,
        VisualVerificationDecision.UNCERTAIN,
        VisualVerificationDecision.REJECT,
    }
