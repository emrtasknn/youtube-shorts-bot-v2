from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.services.scene_contract import SceneContract


class VisualBeatType(StrEnum):
    HOOK = "hook"
    PERSON = "person"
    PLACE = "place"
    EVENT = "event"
    OBJECT = "object"
    ACTION = "action"
    CONSEQUENCE = "consequence"
    PAYOFF = "payoff"
    TRANSITION = "transition"


class VisualSourcePriority(StrEnum):
    EXACT_ENTITY = "exact_entity"
    EXACT_EVENT = "exact_event"
    ARCHIVAL = "archival"
    CONTEXTUAL = "contextual"
    GENERIC = "generic"


@dataclass(frozen=True, slots=True)
class VisualIntent:
    scene_index: int
    primary_entity: str
    secondary_entities: tuple[str, ...]
    action: str
    location: str
    era: str
    event: str
    visual_goal: str
    must_show: tuple[str, ...]
    must_avoid: tuple[str, ...]
    source_priority: VisualSourcePriority
    beat_type: VisualBeatType
    specificity: float
    confidence: float

    def __post_init__(self) -> None:
        if self.scene_index < 0:
            raise ValueError("scene_index must be non-negative")
        if not self.visual_goal.strip():
            raise ValueError("visual_goal is required")
        if not 0 <= self.specificity <= 1:
            raise ValueError("specificity must be between 0 and 1")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.must_show:
            raise ValueError("visual intent must contain at least one must_show signal")


class VisualIntentCompiler:
    """Compiles the existing SceneContract into a deterministic visual intent."""

    def compile(self, scene: SceneContract, *, scene_index: int = 0) -> VisualIntent:
        entities = tuple(dict.fromkeys((*scene.entities, scene.subject)))
        entities = tuple(item for item in entities if item.strip())
        primary = entities[0] if entities else scene.subject.strip()
        secondary = tuple(item for item in entities[1:] if item != primary)

        must_show = tuple(
            dict.fromkeys(
                (
                    *scene.must_show,
                    *(item for item in (primary, scene.action) if item.strip()),
                )
            )
        )
        source_priority = self._source_priority(
            has_entity=bool(primary),
            has_event=bool(scene.purpose and scene.purpose != "support_narration"),
            has_location=bool(scene.location),
        )
        beat_type = self._beat_type(scene)
        specificity = self._specificity(
            primary=primary,
            action=scene.action,
            must_show=must_show,
            visual_goal=scene.visual_goal,
        )
        confidence = min(
            1.0,
            0.45
            + (0.20 if primary else 0.0)
            + (0.15 if scene.action else 0.0)
            + (0.10 if scene.location else 0.0)
            + (0.10 if scene.era else 0.0),
        )
        return VisualIntent(
            scene_index=scene_index,
            primary_entity=primary,
            secondary_entities=secondary,
            action=scene.action,
            location=scene.location,
            era=scene.era,
            event=scene.purpose,
            visual_goal=scene.visual_goal,
            must_show=must_show,
            must_avoid=scene.must_avoid,
            source_priority=source_priority,
            beat_type=beat_type,
            specificity=specificity,
            confidence=confidence,
        )

    @staticmethod
    def _source_priority(
        *, has_entity: bool, has_event: bool, has_location: bool
    ) -> VisualSourcePriority:
        if has_entity and has_event:
            return VisualSourcePriority.EXACT_EVENT
        if has_entity:
            return VisualSourcePriority.EXACT_ENTITY
        if has_location:
            return VisualSourcePriority.CONTEXTUAL
        return VisualSourcePriority.GENERIC

    @staticmethod
    def _beat_type(scene: SceneContract) -> VisualBeatType:
        purpose = scene.purpose.lower()
        if "hook" in purpose:
            return VisualBeatType.HOOK
        if "payoff" in purpose or "conclusion" in purpose:
            return VisualBeatType.PAYOFF
        if scene.action:
            return VisualBeatType.ACTION
        if scene.location:
            return VisualBeatType.PLACE
        if scene.entities:
            return VisualBeatType.PERSON
        return VisualBeatType.TRANSITION

    @staticmethod
    def _specificity(
        *,
        primary: str,
        action: str,
        must_show: tuple[str, ...],
        visual_goal: str,
    ) -> float:
        signals = sum(
            (
                bool(primary),
                bool(action),
                len(must_show) >= 2,
                len(visual_goal.split()) >= 4,
            )
        )
        return min(1.0, 0.25 * signals)
