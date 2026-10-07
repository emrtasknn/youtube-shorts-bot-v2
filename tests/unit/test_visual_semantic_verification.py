import pytest

from app.application.services.visual_semantic_verification import (
    VisualSemanticScore,
    VisualVerificationDecision,
    VisualVerificationPolicy,
    VisualVerificationResult,
)


def test_visual_semantic_score_rejects_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        VisualSemanticScore(
            entity_match=1.0,
            action_match=0.8,
            context_match=0.8,
            must_show_match=1.1,
            must_avoid_compliance=1.0,
            overall=0.9,
        )


@pytest.mark.parametrize(
    ("overall", "decision"),
    [
        (0.90, VisualVerificationDecision.ACCEPT),
        (0.65, VisualVerificationDecision.ACCEPT_DEGRADED),
        (0.50, VisualVerificationDecision.UNCERTAIN),
        (0.20, VisualVerificationDecision.REJECT),
    ],
)
def test_policy_maps_semantic_score_to_safe_decision(
    overall: float,
    decision: VisualVerificationDecision,
) -> None:
    score = VisualSemanticScore(
        entity_match=overall,
        action_match=overall,
        context_match=overall,
        must_show_match=overall,
        must_avoid_compliance=overall,
        overall=overall,
    )

    assert VisualVerificationPolicy().decide(score) == decision


def test_policy_rejects_invalid_threshold_order() -> None:
    with pytest.raises(ValueError, match="strictly descending"):
        VisualVerificationPolicy(
            accept_threshold=0.70,
            degraded_threshold=0.75,
            uncertainty_threshold=0.40,
        )


def test_result_exposes_retry_and_acceptance_semantics() -> None:
    score = VisualSemanticScore(
        entity_match=0.9,
        action_match=0.7,
        context_match=0.8,
        must_show_match=0.9,
        must_avoid_compliance=1.0,
        overall=0.82,
    )
    result = VisualVerificationResult(
        decision=VisualVerificationDecision.ACCEPT,
        score=score,
        verifier="deterministic-v1",
        matched_signals=("Roman army", "Alps"),
    )

    assert result.accepted is True
    assert result.requires_retry is False
    assert result.missing_signals == ()
