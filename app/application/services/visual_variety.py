from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VisualVarietyProfile:
    asset_id: str
    provider: str
    subject_tokens: frozenset[str]
    composition: str
    shot_type: str


@dataclass(frozen=True, slots=True)
class VisualVarietyDecision:
    score: float
    duplicate: bool
    penalties: tuple[str, ...]
    signals: tuple[str, ...]


class VisualVarietyEngine:
    """Ranks already-relevant candidates to reduce visual repetition.

    Variety is a secondary objective: callers must run semantic/quality gates
    first or use this engine only to order a bounded verification shortlist.
    """

    _SHOT_TYPES = {
        "close_up": ("close-up", "close up", "closeup", "detail shot", "macro"),
        "wide": ("wide shot", "wide view", "panorama", "aerial", "overhead", "landscape"),
        "portrait": ("portrait", "headshot", "face", "person"),
        "group": ("group", "crowd", "team", "people"),
        "interior": ("interior", "inside", "room", "indoors"),
        "exterior": ("exterior", "outside", "outdoors", "street"),
    }

    def __init__(self, *, max_history: int = 24) -> None:
        if max_history < 1:
            raise ValueError("max_history must be positive")
        self._max_history = max_history
        self._history: dict[str, list[VisualVarietyProfile]] = {}

    def rank(
        self,
        candidates: list[Any],
        *,
        run_id: str,
        subject_terms: tuple[str, ...] = (),
    ) -> list[Any]:
        history = self._history.setdefault(run_id, [])
        if not history:
            return list(candidates)
        scored = [
            (
                self.evaluate(
                    self._profile(candidate, subject_terms=subject_terms),
                    history=history,
                ),
                index,
                candidate,
            )
            for index, candidate in enumerate(candidates)
        ]
        return [
            candidate
            for _, _, candidate in sorted(
                scored,
                key=lambda entry: (
                    entry[0].duplicate,
                    -entry[0].score,
                    -entry[1],
                ),
            )
        ]

    def profile(self, candidate: Any, *, subject_terms: tuple[str, ...] = ()) -> VisualVarietyProfile:
        return self._profile(candidate, subject_terms=subject_terms)

    def history(self, run_id: str) -> list[VisualVarietyProfile]:
        return list(self._history.get(run_id, []))

    def evaluate(
        self,
        profile: VisualVarietyProfile,
        *,
        history: list[VisualVarietyProfile],
    ) -> VisualVarietyDecision:
        if not history:
            return VisualVarietyDecision(
                score=1.0,
                duplicate=False,
                penalties=(),
                signals=("first_visual",),
            )

        penalties: list[str] = []
        signals: list[str] = []
        duplicate = any(item.asset_id == profile.asset_id for item in history)

        if duplicate:
            penalties.append("exact_asset_reuse")
            return VisualVarietyDecision(
                score=0.0,
                duplicate=True,
                penalties=tuple(penalties),
                signals=(),
            )

        score = 1.0
        provider_reuse = any(item.provider == profile.provider for item in history[-4:])
        if provider_reuse:
            score -= 0.12
            penalties.append("recent_provider_reuse")

        same_composition = any(
            item.composition == profile.composition for item in history[-3:] if item.composition
        )
        if same_composition:
            score -= 0.18
            penalties.append("recent_composition_reuse")

        same_shot = any(
            item.shot_type == profile.shot_type for item in history[-3:] if item.shot_type
        )
        if same_shot:
            score -= 0.15
            penalties.append("recent_shot_type_reuse")

        overlap = max(
            (self._jaccard(profile.subject_tokens, item.subject_tokens) for item in history[-3:]),
            default=0.0,
        )
        if overlap >= 0.75:
            score -= 0.20
            penalties.append("high_subject_overlap")
        elif overlap >= 0.45:
            score -= 0.08
            penalties.append("moderate_subject_overlap")

        if provider_reuse is False:
            signals.append("provider_variety")
        if same_composition is False:
            signals.append("composition_variety")
        if same_shot is False:
            signals.append("shot_type_variety")
        if overlap < 0.45:
            signals.append("subject_variety")

        return VisualVarietyDecision(
            score=max(0.0, min(1.0, score)),
            duplicate=False,
            penalties=tuple(penalties),
            signals=tuple(signals),
        )

    def remember(
        self,
        *,
        run_id: str,
        item: dict[str, Any],
        provider: str,
        subject_terms: tuple[str, ...] = (),
    ) -> None:
        history = self._history.setdefault(run_id, [])
        history.append(self._profile_from_item(item, provider, subject_terms))
        del history[: -self._max_history]

    def history_size(self, run_id: str) -> int:
        return len(self._history.get(run_id, []))

    @classmethod
    def _profile(cls, candidate: Any, *, subject_terms: tuple[str, ...]) -> VisualVarietyProfile:
        item = candidate.item if hasattr(candidate, "item") else candidate
        provider_values = getattr(candidate, "providers", ())
        provider = str(
            getattr(candidate, "provider", "")
            or (provider_values[0] if provider_values else "")
            or item.get("_provider", "")
        )
        return cls._profile_from_item(item, provider, subject_terms)

    @classmethod
    def _profile_from_item(
        cls,
        item: dict[str, Any],
        provider: str,
        subject_terms: tuple[str, ...],
    ) -> VisualVarietyProfile:
        text_parts = [
            str(item.get(key, ""))
            for key in ("title", "description", "alt", "tags", "url", "photographer")
        ]
        text_parts.extend(subject_terms)
        text = " ".join(text_parts).lower()
        tokens = frozenset(token for token in re.findall(r"[a-z0-9]+", text) if len(token) > 2)
        width = cls._number(item.get("width"))
        height = cls._number(item.get("height"))
        ratio = width / height if width and height else 0.0
        if ratio >= 0.72:
            composition = "portrait_frame"
        elif ratio <= 0.58:
            composition = "tall_frame"
        else:
            composition = "balanced_frame"

        shot_type = next(
            (
                name
                for name, markers in cls._SHOT_TYPES.items()
                if any(marker in text for marker in markers)
            ),
            "",
        )
        return VisualVarietyProfile(
            asset_id=str(item.get("id") or item.get("asset_id") or ""),
            provider=provider,
            subject_tokens=tokens,
            composition=composition,
            shot_type=shot_type,
        )

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
        union = left | right
        if not union:
            return 0.0
        return len(left & right) / len(union)
