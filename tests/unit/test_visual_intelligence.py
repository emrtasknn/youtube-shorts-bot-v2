from app.application.services.scene_contract import build_scene_contract
from app.application.services.visual_decision import (
    VisualDecision,
    VisualDecisionEngine,
)
from app.application.services.visual_intent import (
    VisualBeatType,
    VisualIntentCompiler,
    VisualSourcePriority,
)


def _scene() -> object:
    return build_scene_contract(
        {
            "narration": "Al Jolson starred in The Jazz Singer in 1927.",
            "visual_goal": "Show Al Jolson performing in The Jazz Singer.",
            "visual_query": "Al Jolson The Jazz Singer 1927",
            "purpose": "event",
            "subject": "Al Jolson",
            "action": "performing",
            "entities": ["Al Jolson", "The Jazz Singer"],
            "location": "Hollywood",
            "era": "1927",
            "must_show": ["Al Jolson", "The Jazz Singer"],
        }
    )


def test_compiler_creates_specific_visual_intent() -> None:
    intent = VisualIntentCompiler().compile(_scene(), scene_index=2)

    assert intent.scene_index == 2
    assert intent.primary_entity == "Al Jolson"
    assert intent.secondary_entities == ("The Jazz Singer",)
    assert intent.source_priority == VisualSourcePriority.EXACT_EVENT
    assert intent.beat_type == VisualBeatType.ACTION
    assert "Al Jolson" in intent.must_show
    assert intent.specificity >= 0.75
    assert intent.confidence >= 0.80


def test_beautiful_wrong_visual_never_beats_relevant_visual() -> None:
    result = VisualDecisionEngine().decide(
        semantic_relevance=0.42,
        visual_quality=0.98,
        factual_specificity=0.10,
        source_is_exact=False,
    )

    assert result.decision == VisualDecision.REJECT_NO_SAFE_VISUAL


def test_relevant_but_ugly_visual_is_beautified() -> None:
    result = VisualDecisionEngine().decide(
        semantic_relevance=0.95,
        visual_quality=0.45,
        factual_specificity=0.95,
        source_is_exact=True,
        beautifiable=True,
    )

    assert result.decision == VisualDecision.BEAUTIFY_THEN_ACCEPT
    assert result.enhancement_required is True


def test_exact_good_visual_is_accepted() -> None:
    result = VisualDecisionEngine().decide(
        semantic_relevance=0.95,
        visual_quality=0.90,
        factual_specificity=0.95,
        source_is_exact=True,
    )

    assert result.decision == VisualDecision.ACCEPT_EXACT


def test_relevant_non_beautifiable_visual_is_kept_as_fallback() -> None:
    result = VisualDecisionEngine().decide(
        semantic_relevance=0.72,
        visual_quality=0.30,
        factual_specificity=0.80,
        source_is_exact=True,
        beautifiable=False,
    )

    assert result.decision == VisualDecision.FALLBACK_RELEVANT
