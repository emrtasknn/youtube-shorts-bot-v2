from app.application.services.scene_contract import build_scene_contract
from app.application.services.visual_relevance import (
    VisualRelevanceContext,
    VisualRelevanceScorer,
)


def _context() -> VisualRelevanceContext:
    scene = build_scene_contract(
        {
            "narration": "The Roman Forum was the center of public life.",
            "visual_goal": "Show the Roman Forum as a historical location.",
            "visual_query": "Roman Forum ancient Rome ruins",
            "entities": ["Roman Forum"],
            "location": "Rome",
            "era": "ancient Rome",
            "action": "show ruins",
            "must_show": ["forum ruins"],
            "must_avoid": ["modern skyline"],
        }
    )
    return VisualRelevanceContext.from_scene(scene)


def test_relevance_prefers_scene_specific_asset() -> None:
    scorer = VisualRelevanceScorer()
    context = _context()

    relevant = scorer.score(
        {
            "id": "relevant",
            "alt": "Roman Forum ancient Rome ruins, forum ruins",
        },
        query="Roman Forum ancient Rome ruins",
        context=context,
    )
    generic = scorer.score(
        {
            "id": "generic",
            "alt": "beautiful old ruins in a city",
        },
        query="Roman Forum ancient Rome ruins",
        context=context,
    )

    assert relevant.score > generic.score
    assert "entity:roman" in relevant.matched_terms
    assert "missing_must_show_terms" not in relevant.reasons


def test_relevance_penalizes_must_avoid_match() -> None:
    result = VisualRelevanceScorer().score(
        {"alt": "Roman Forum ruins with modern skyline"},
        query="Roman Forum ruins",
        context=_context(),
    )

    assert result.score < 0.30
    assert "must_avoid_match" in result.reasons


def test_relevance_without_context_remains_query_based() -> None:
    result = VisualRelevanceScorer().score(
        {"alt": "ancient roman forum ruins"},
        query="roman forum",
    )

    assert result.score == 1.0
    assert result.reasons == ()
