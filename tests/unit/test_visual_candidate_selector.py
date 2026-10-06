from app.application.services.stock_media_scoring import StockMediaScore
from app.application.services.visual_candidate_selector import VisualCandidateSelector
from app.application.services.visual_decision import VisualDecision
from app.application.services.visual_intent import (
    VisualBeatType,
    VisualIntent,
    VisualSourcePriority,
)


def _intent() -> VisualIntent:
    return VisualIntent(
        scene_index=0,
        primary_entity="Al Jolson",
        secondary_entities=("The Jazz Singer",),
        action="performing",
        location="Hollywood",
        era="1927",
        event="event",
        visual_goal="Show Al Jolson performing in The Jazz Singer.",
        must_show=("Al Jolson", "The Jazz Singer"),
        must_avoid=(),
        source_priority=VisualSourcePriority.EXACT_EVENT,
        beat_type=VisualBeatType.ACTION,
        specificity=0.75,
        confidence=0.90,
    )


def _score(
    *,
    relevance: float,
    orientation: float,
    resolution: float,
    duration: float = 1.0,
) -> StockMediaScore:
    return StockMediaScore(
        score=relevance,
        relevance=relevance,
        orientation=orientation,
        resolution=resolution,
        duration=duration,
        duplicate_penalty=0.0,
        eligible=True,
        reasons=(),
        matched_terms=("al", "jolson"),
    )


def test_selector_prefers_semantically_strong_exact_candidate() -> None:
    selector = VisualCandidateSelector()
    result = selector.select(
        [
            ({"id": "beautiful-wrong"}, _score(
                relevance=0.42,
                orientation=1.0,
                resolution=1.0,
            )),
            ({"id": "relevant-exact"}, _score(
                relevance=0.95,
                orientation=1.0,
                resolution=0.70,
            )),
        ],
        intent=_intent(),
        source_is_exact=True,
    )

    assert result is not None
    assert result.item["id"] == "relevant-exact"
    assert result.evidence.decision == VisualDecision.ACCEPT_EXACT


def test_selector_keeps_relevant_candidate_when_beautification_is_needed() -> None:
    selector = VisualCandidateSelector()
    result = selector.select(
        [
            ({"id": "relevant-ugly"}, _score(
                relevance=0.95,
                orientation=1.0,
                resolution=0.35,
            )),
        ],
        intent=_intent(),
        source_is_exact=True,
    )

    assert result is not None
    assert result.item["id"] == "relevant-ugly"
    assert result.evidence.decision == VisualDecision.BEAUTIFY_THEN_ACCEPT


def test_selector_rejects_only_beautiful_but_irrelevant_candidate() -> None:
    selector = VisualCandidateSelector()
    result = selector.select(
        [
            ({"id": "wrong"}, _score(
                relevance=0.30,
                orientation=1.0,
                resolution=1.0,
            )),
        ],
        intent=_intent(),
        source_is_exact=False,
    )

    assert result is None
