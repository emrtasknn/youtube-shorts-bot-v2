from __future__ import annotations

from app.application.services.visual_beat import VisualBeat
from app.application.services.visual_relevance import VisualRelevanceContext


def to_visual_relevance_context(beat: VisualBeat) -> VisualRelevanceContext:
    """Adapt one timed visual beat to the existing M17 retrieval contract."""

    return VisualRelevanceContext(
        entities=beat.entities,
        location=beat.location,
        era=beat.era,
        visual_goal=beat.visual_goal,
        action=beat.action,
        must_show=beat.must_show,
        must_avoid=beat.must_avoid,
    )
