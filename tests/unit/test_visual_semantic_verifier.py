import pytest

from app.application.services.visual_semantic_verification import (
    VisualVerificationDecision,
)
from app.application.services.visual_semantic_verifier import (
    DeterministicVisualSemanticVerifier,
    VisualVerificationContext,
)


def test_deterministic_verifier_accepts_strong_metadata_match() -> None:
    verifier = DeterministicVisualSemanticVerifier()
    result = verifier.verify(
        {
            "title": "Roman army crossing the Alps",
            "description": "Ancient Roman soldiers crossing snowy Alps",
            "alt": "Roman army in the Alps",
            "tags": ["Roman", "army", "Alps"],
        },
        context=VisualVerificationContext(
            entities=("Roman army",),
            location="Alps",
            era="ancient",
            action="crossing",
            must_show=("Roman army", "Alps"),
        ),
    )

    assert result.decision == VisualVerificationDecision.ACCEPT
    assert result.score.overall >= 0.78
    assert result.verifier == "deterministic-metadata-v1"
    assert result.violated_constraints == ()


def test_deterministic_verifier_rejects_must_avoid_match() -> None:
    verifier = DeterministicVisualSemanticVerifier()
    result = verifier.verify(
        {
            "title": "Roman army reenactment",
            "description": "Modern soldiers in Roman costumes",
        },
        context=VisualVerificationContext(
            entities=("Roman army",),
            must_avoid=("modern soldiers",),
        ),
    )

    assert result.score.must_avoid_compliance == 0.0
    assert "must_avoid:modern soldiers" in result.violated_constraints
    assert result.decision == VisualVerificationDecision.REJECT


def test_deterministic_verifier_reports_missing_signals() -> None:
    verifier = DeterministicVisualSemanticVerifier()
    result = verifier.verify(
        {"title": "Mountain landscape"},
        context=VisualVerificationContext(
            entities=("Roman army",),
            location="Alps",
            action="crossing",
            must_show=("Roman army",),
        ),
    )

    assert result.decision in {
        VisualVerificationDecision.UNCERTAIN,
        VisualVerificationDecision.REJECT,
    }
    assert "Roman army" in result.missing_signals
    assert "Alps" in result.missing_signals
    assert "crossing" in result.missing_signals


def test_empty_intent_does_not_falsely_accept() -> None:
    verifier = DeterministicVisualSemanticVerifier()
    result = verifier.verify(
        {"title": "Anything"},
        context=VisualVerificationContext(),
    )

    assert result.score.overall == pytest.approx(0.10)
    assert result.decision == VisualVerificationDecision.REJECT


def test_list_metadata_is_searchable() -> None:
    verifier = DeterministicVisualSemanticVerifier()
    result = verifier.verify(
        {"tags": ["Roman", "Alps", "army"]},
        context=VisualVerificationContext(entities=("Roman army",)),
    )

    assert result.score.entity_match == pytest.approx(0.0)
    assert result.score.must_avoid_compliance == pytest.approx(1.0)
