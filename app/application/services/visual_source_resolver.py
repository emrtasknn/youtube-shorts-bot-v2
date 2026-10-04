from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.application.services.scene_contract import SceneContract

VisualSourceKind = Literal["stock"]


@dataclass(frozen=True, slots=True)
class VisualSourcePlan:
    """Deterministic plan describing how a scene should obtain its visual asset."""

    kind: VisualSourceKind
    exact_query: str
    broader_queries: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "exact_query": self.exact_query,
            "broader_queries": list(self.broader_queries),
            "reason": self.reason,
        }


class VisualSourceResolver:
    """Resolve a scene into an explicit visual-source plan without calling providers."""

    def resolve(self, scene: SceneContract) -> VisualSourcePlan:
        exact_query = self._exact_query(scene)
        broader_queries = self._broader_queries(scene, exact_query)
        return VisualSourcePlan(
            kind="stock",
            exact_query=exact_query,
            broader_queries=broader_queries,
            reason=self._reason(scene),
        )

    @staticmethod
    def _exact_query(scene: SceneContract) -> str:
        query = scene.visual_query.strip()
        if not query:
            raise ValueError("Scene visual_query must not be empty")
        return query

    @staticmethod
    def _broader_queries(
        scene: SceneContract, exact_query: str
    ) -> tuple[str, ...]:
        candidates = (
            scene.visual_goal.strip(),
            f"{scene.era.strip()} historical illustration" if scene.era.strip() else "",
            f"{scene.location.strip()} historical illustration"
            if scene.location.strip()
            else "",
            "historical illustration",
        )
        unique: list[str] = []
        for candidate in candidates:
            if candidate and candidate != exact_query and candidate not in unique:
                unique.append(candidate)
        return tuple(unique)

    @staticmethod
    def _reason(scene: SceneContract) -> str:
        if scene.must_show:
            return "stock_selected_with_explicit_must_show_constraints"
        if scene.entities or scene.location or scene.era:
            return "stock_selected_for_concrete_scene_context"
        return "stock_selected_as_current_m5_compatible_source"
