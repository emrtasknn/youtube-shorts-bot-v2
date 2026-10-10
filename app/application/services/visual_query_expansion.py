from __future__ import annotations

import re
from dataclasses import dataclass

from app.application.services.scene_contract import SceneContract


@dataclass(frozen=True, slots=True)
class VisualQueryVariant:
    name: str
    query: str
    priority: int
    min_relevance: float = 0.10


@dataclass(frozen=True, slots=True)
class VisualQueryPlan:
    variants: tuple[VisualQueryVariant, ...]
    max_queries: int = 5

    def __post_init__(self) -> None:
        if not self.variants:
            raise ValueError("At least one visual query variant is required")
        if self.max_queries < 1:
            raise ValueError("max_queries must be positive")

    @property
    def bounded_variants(self) -> tuple[VisualQueryVariant, ...]:
        return self.variants[: self.max_queries]


def looks_historical_era(era: str) -> bool:
    """Recognize years, decade labels (for example 1980s), and historical eras."""
    normalized = era.lower()
    return bool(
        re.search(
            r"\b(?:\d{3,4}s?|ancient|medieval|roman|soviet|century|bc|ad)\b",
            normalized,
        )
    )


class VisualQueryExpander:
    """Build a bounded, scene-specific query portfolio for asset retrieval."""

    def expand(self, scene: SceneContract) -> VisualQueryPlan:
        entity = next(
            (value.strip() for value in scene.entities if value.strip()), scene.subject.strip()
        )
        action = scene.action.strip()
        location = scene.location.strip()
        era = scene.era.strip()
        must_show = self._join(*scene.must_show)

        candidates: tuple[tuple[str, str, int], ...]
        if self._looks_historical(era):
            # Historic archives often index images by the visible object, not by
            # the narration's abstract event. Give must_show its own search slot.
            # Keep one archival query, but spend the remaining budget on the
            # concrete subject/action/context rather than near-duplicate archive terms.
            candidates = (
                ("primary", scene.visual_query.strip(), 100),
                ("must_show", self._join(must_show, entity, location, era), 95),
                ("entity_action", self._join(entity, action, location, era), 90),
                ("entity_context", self._join(entity, location or era), 80),
                ("archive_subject", self._join(scene.subject.strip() or entity, location, era, "historical illustration"), 70),
            )
        else:
            candidates = (
                ("primary", scene.visual_query.strip(), 100),
                ("entity_action", self._join(entity, action), 90),
                ("entity_context", self._join(entity, location or era), 80),
                ("goal_context", self._join(scene.visual_goal.strip(), location or era), 70),
                ("contextual", self._join(location, era, "documentary photograph"), 50),
                ("goal", scene.visual_goal.strip(), 40),
            )

        variants: list[VisualQueryVariant] = []
        seen: set[str] = set()
        for name, query, priority in candidates:
            normalized = self._normalize(query)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            variants.append(
                VisualQueryVariant(
                    name=name,
                    query=query,
                    priority=priority,
                    min_relevance=0.08 if name in {"contextual", "must_show"} else 0.10,
                )
            )

        return VisualQueryPlan(tuple(variants))

    @staticmethod
    def _join(*parts: str) -> str:
        return " ".join(part for part in parts if part).strip()

    @staticmethod
    def _looks_historical(era: str) -> bool:
        return looks_historical_era(era)

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))
