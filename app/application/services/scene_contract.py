from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SceneContract:
    """Structured visual contract shared by storyboard and asset selection."""

    narration: str
    visual_goal: str
    visual_query: str
    purpose: str
    subject: str
    action: str
    entities: tuple[str, ...]
    location: str
    era: str
    visual_intent: str
    visual_style: str
    must_show: tuple[str, ...]
    must_avoid: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "narration": self.narration,
            "visual_goal": self.visual_goal,
            "visual_query": self.visual_query,
            "purpose": self.purpose,
            "subject": self.subject,
            "action": self.action,
            "entities": list(self.entities),
            "location": self.location,
            "era": self.era,
            "visual_intent": self.visual_intent,
            "visual_style": self.visual_style,
            "must_show": list(self.must_show),
            "must_avoid": list(self.must_avoid),
        }


def build_scene_contract(item: dict[str, Any]) -> SceneContract:
    if not isinstance(item, dict):
        raise ValueError("Scene must be an object")

    def required_text(name: str) -> str:
        value = str(item.get(name) or "").strip()
        if not value:
            raise ValueError(f"Every scene needs {name}")
        return value

    def optional_text(name: str) -> str:
        return str(item.get(name) or "").strip()

    def string_tuple(name: str) -> tuple[str, ...]:
        value = item.get(name, [])
        if value is None:
            return ()
        if not isinstance(value, list):
            raise ValueError(f"Scene {name} must be a list")
        return tuple(str(entry).strip() for entry in value if str(entry).strip())

    narration = required_text("narration")
    visual_goal = required_text("visual_goal")
    visual_query = required_text("visual_query")

    return SceneContract(
        narration=narration,
        visual_goal=visual_goal,
        visual_query=visual_query,
        purpose=optional_text("purpose") or "support_narration",
        subject=optional_text("subject") or visual_query,
        action=optional_text("action"),
        entities=string_tuple("entities"),
        location=optional_text("location"),
        era=optional_text("era"),
        visual_intent=optional_text("visual_intent") or visual_goal,
        visual_style=optional_text("visual_style") or "documentary",
        must_show=string_tuple("must_show"),
        must_avoid=string_tuple("must_avoid"),
    )
