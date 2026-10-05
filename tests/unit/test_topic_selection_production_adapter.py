from uuid import uuid4

import pytest

from app.application.services.topic_selection_production_adapter import (
    TopicSelectionProductionAdapter,
)
from app.domain.topic_optimization import (
    TopicDecisionStatus,
    TopicScore,
    TopicSelectionDecision,
)


def _selected(topic: str) -> TopicSelectionDecision:
    candidate_id = uuid4()
    return TopicSelectionDecision(
        decision_id=uuid4(),
        status=TopicDecisionStatus.SELECTED,
        selected_candidate_id=candidate_id,
        selected_topic=topic,
        candidate_ids=(candidate_id,),
        selected_score=TopicScore(candidate_id=candidate_id, total=0.9),
    )


def test_selected_decision_overrides_manual_topic() -> None:
    adapter = TopicSelectionProductionAdapter(_selected("Selected history topic"))

    assert adapter.resolve_topic("Manual topic") == "Selected history topic"


def test_no_selection_preserves_manual_topic() -> None:
    decision = TopicSelectionDecision.no_selection(decision_id=uuid4())
    adapter = TopicSelectionProductionAdapter(decision)

    assert adapter.resolve_topic("Manual topic") == "Manual topic"


def test_missing_decision_uses_manual_topic() -> None:
    assert TopicSelectionProductionAdapter().resolve_topic("Manual topic") == "Manual topic"


def test_blank_manual_topic_is_rejected_without_selection() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        TopicSelectionProductionAdapter().resolve_topic("   ")


def test_no_selection_requires_manual_fallback() -> None:
    decision = TopicSelectionDecision.no_selection(decision_id=uuid4())

    with pytest.raises(ValueError, match="fallback topic"):
        TopicSelectionProductionAdapter(decision).resolve_topic("   ")
