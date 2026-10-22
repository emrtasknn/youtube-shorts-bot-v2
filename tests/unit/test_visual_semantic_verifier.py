import pytest

from app.application.services.visual_semantic_verification import (
    VisualSemanticScore,
    VisualVerificationDecision,
    VisualVerificationResult,
)
from app.application.services.visual_semantic_verifier import (
    DeterministicVisualSemanticVerifier,
    FailoverVisualSemanticVerifier,
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

    assert result.score.entity_match == pytest.approx(1.0)
    assert result.score.must_avoid_compliance == pytest.approx(1.0)


def test_failover_verifier_uses_fallback_when_primary_is_unavailable() -> None:
    class FailingVerifier:
        name = "vision-provider"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            raise RuntimeError("vision provider unavailable")

    fallback = DeterministicVisualSemanticVerifier()
    verifier = FailoverVisualSemanticVerifier(FailingVerifier(), fallback)

    result = verifier.verify(
        {"title": "Roman army crossing the Alps"},
        context=VisualVerificationContext(
            entities=("Roman army",),
            location="Alps",
            action="crossing",
        ),
    )

    assert result.verifier == "failover:deterministic-metadata-v1"
    assert result.decision in {
        VisualVerificationDecision.ACCEPT,
        VisualVerificationDecision.ACCEPT_DEGRADED,
    }


def test_failover_verifier_does_not_override_primary_rejection() -> None:
    class RejectingVerifier:
        name = "vision-provider"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            result = DeterministicVisualSemanticVerifier().verify(
                {"title": "Modern city"},
                context=VisualVerificationContext(
                    must_avoid=("modern city",),
                ),
            )
            return VisualVerificationResult(
                decision=result.decision,
                score=result.score,
                verifier="vision-provider",
                matched_signals=result.matched_signals,
                missing_signals=result.missing_signals,
                violated_constraints=result.violated_constraints,
            )

    class AcceptingFallback:
        name = "fallback"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            return DeterministicVisualSemanticVerifier().verify(
                {"title": "Roman army"},
                context=VisualVerificationContext(entities=("Roman army",)),
            )

    verifier = FailoverVisualSemanticVerifier(RejectingVerifier(), AcceptingFallback())
    result = verifier.verify(
        {},
        context=VisualVerificationContext(entities=("Roman army",)),
    )

    assert result.verifier == "vision-provider"
    assert result.decision == VisualVerificationDecision.REJECT


def test_metadata_fallback_accepts_partial_historical_context_without_false_identity() -> None:
    verifier = DeterministicVisualSemanticVerifier()
    result = verifier.verify(
        {
            "title": "Ancient Roman stone relief",
            "description": "Roman carving from an archaeological collection",
            "tags": ["Rome", "ancient", "relief"],
        },
        context=VisualVerificationContext(
            entities=("Roman",),
            location="Roman Forum",
            era="Roman Republic era",
            must_show=("display of ancient stone carving", "fasces with axe"),
            must_avoid=("modern military",),
        ),
    )

    assert result.decision == VisualVerificationDecision.ACCEPT_DEGRADED
    assert result.score.entity_match == pytest.approx(1.0)
    assert result.score.context_match > 0.0
    assert result.violated_constraints == ()


def test_failover_allows_degraded_match_when_metadata_is_partial() -> None:
    class FailingVerifier:
        name = "vision-provider"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            raise RuntimeError("vision provider unavailable")

    class PartialMetadataVerifier:
        name = "deterministic-metadata-v1"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            return VisualVerificationResult(
                decision=VisualVerificationDecision.REJECT,
                score=VisualSemanticScore(
                    entity_match=0.3,
                    action_match=0.0,
                    context_match=0.4,
                    must_show_match=0.0,
                    must_avoid_compliance=1.0,
                    overall=0.32,
                ),
                verifier=self.name,
                matched_signals=("entity:roman",),
                missing_signals=("fasces with axe",),
            )

    result = FailoverVisualSemanticVerifier(
        FailingVerifier(),
        PartialMetadataVerifier(),
    ).verify(
        {"title": "Roman historical artifact"},
        context=VisualVerificationContext(entities=("Roman",)),
    )

    assert result.decision == VisualVerificationDecision.ACCEPT_DEGRADED
    assert result.score.overall == pytest.approx(0.32)
    assert result.violated_constraints == ()


def test_failover_never_bypasses_must_avoid_violations() -> None:
    class FailingVerifier:
        name = "vision-provider"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            raise RuntimeError("vision provider unavailable")

    class UnsafeMetadataVerifier:
        name = "deterministic-metadata-v1"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            return VisualVerificationResult(
                decision=VisualVerificationDecision.REJECT,
                score=VisualSemanticScore(
                    entity_match=0.3,
                    action_match=0.0,
                    context_match=0.4,
                    must_show_match=0.0,
                    must_avoid_compliance=0.0,
                    overall=0.22,
                ),
                verifier=self.name,
                matched_signals=("entity:roman",),
                violated_constraints=("must_avoid:modern military",),
            )

    result = FailoverVisualSemanticVerifier(
        FailingVerifier(),
        UnsafeMetadataVerifier(),
    ).verify(
        {"title": "Roman historical artifact"},
        context=VisualVerificationContext(
            entities=("Roman",),
            must_avoid=("modern military",),
        ),
    )

    assert result.decision == VisualVerificationDecision.REJECT
    assert result.violated_constraints == ("must_avoid:modern military",)


def test_failover_accepts_strong_historical_context_when_entity_metadata_is_missing() -> None:
    class FailingVerifier:
        name = "vision-provider"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            raise RuntimeError("vision provider unavailable")

    class ContextOnlyMetadataVerifier:
        name = "deterministic-metadata-v1"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            return VisualVerificationResult(
                decision=VisualVerificationDecision.REJECT,
                score=VisualSemanticScore(
                    entity_match=0.0,
                    action_match=0.0,
                    context_match=0.8,
                    must_show_match=0.0,
                    must_avoid_compliance=1.0,
                    overall=0.34,
                ),
                verifier=self.name,
                matched_signals=("context:ancient Rome",),
                missing_signals=("Roman soldiers",),
            )

    result = FailoverVisualSemanticVerifier(
        FailingVerifier(),
        ContextOnlyMetadataVerifier(),
    ).verify(
        {"title": "Ancient Roman historical relief"},
        context=VisualVerificationContext(
            entities=("Roman soldiers",),
            era="ancient Rome",
        ),
    )

    assert result.decision == VisualVerificationDecision.ACCEPT_DEGRADED
    assert result.score.overall == pytest.approx(0.34)
    assert result.violated_constraints == ()


def test_failover_rejects_historical_context_below_grounding_threshold() -> None:
    class FailingVerifier:
        name = "vision-provider"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            raise RuntimeError("vision provider unavailable")

    class WeakContextMetadataVerifier:
        name = "deterministic-metadata-v1"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            return VisualVerificationResult(
                decision=VisualVerificationDecision.REJECT,
                score=VisualSemanticScore(
                    entity_match=0.0,
                    action_match=0.0,
                    context_match=0.4,
                    must_show_match=0.0,
                    must_avoid_compliance=1.0,
                    overall=0.22,
                ),
                verifier=self.name,
                matched_signals=("context:somewhat historical",),
            )

    result = FailoverVisualSemanticVerifier(
        FailingVerifier(),
        WeakContextMetadataVerifier(),
    ).verify(
        {},
        context=VisualVerificationContext(
            entities=("Roman soldiers",),
            era="ancient Rome",
        ),
    )

    assert result.decision == VisualVerificationDecision.REJECT


def test_failover_accepts_grounded_partial_match_below_old_threshold() -> None:
    class FailingVerifier:
        name = "vision-provider"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            raise RuntimeError("vision provider unavailable")

    class PartialMetadataVerifier:
        name = "deterministic-metadata-v1"

        def verify(
            self,
            item: dict[str, object],
            *,
            context: VisualVerificationContext,
        ) -> VisualVerificationResult:
            return VisualVerificationResult(
                decision=VisualVerificationDecision.REJECT,
                score=VisualSemanticScore(
                    entity_match=0.5,
                    action_match=0.0,
                    context_match=0.3,
                    must_show_match=0.0,
                    must_avoid_compliance=1.0,
                    overall=0.28,
                ),
                verifier=self.name,
                matched_signals=("entity:roman", "context:ancient"),
                missing_signals=("c. 113 CE",),
            )

    result = FailoverVisualSemanticVerifier(
        FailingVerifier(),
        PartialMetadataVerifier(),
    ).verify(
        {"title": "Roman historical relief"},
        context=VisualVerificationContext(
            entities=("Roman commander",),
            era="c. 113 CE",
        ),
    )

    assert result.decision == VisualVerificationDecision.ACCEPT_DEGRADED
    assert result.score.overall == pytest.approx(0.28)
    assert result.violated_constraints == ()
