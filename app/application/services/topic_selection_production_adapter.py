from __future__ import annotations

from dataclasses import dataclass

from app.domain.topic_optimization import TopicDecisionStatus, TopicSelectionDecision


@dataclass(frozen=True, slots=True)
class TopicSelectionProductionAdapter:
    """Translate an audited topic decision into a bounded production topic."""

    decision: TopicSelectionDecision | None = None

    def resolve_topic(self, fallback_topic: str) -> str:
        fallback = fallback_topic.strip()
        if self.decision is None:
            if not fallback:
                raise ValueError("production topic must not be empty")
            return fallback

        if self.decision.status is TopicDecisionStatus.SELECTED:
            topic = (self.decision.selected_topic or "").strip()
            if not topic:
                raise ValueError("selected topic decision must contain a topic")
            return topic

        if not fallback:
            raise ValueError("no-selection topic decision requires a fallback topic")
        return fallback
