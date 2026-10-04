from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.application.services.scene_contract import SceneContract


@dataclass(frozen=True, slots=True)
class VisualRelevanceResult:
    score: float
    matched_terms: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VisualRelevanceContext:
    entities: tuple[str, ...] = ()
    location: str = ""
    era: str = ""
    visual_goal: str = ""
    action: str = ""
    must_show: tuple[str, ...] = ()
    must_avoid: tuple[str, ...] = ()

    @classmethod
    def from_scene(cls, scene: SceneContract) -> VisualRelevanceContext:
        return cls(
            entities=scene.entities,
            location=scene.location,
            era=scene.era,
            visual_goal=scene.visual_goal,
            action=scene.action,
            must_show=scene.must_show,
            must_avoid=scene.must_avoid,
        )


class VisualRelevanceScorer:
    """Deterministic scene-to-asset relevance scoring without external model calls."""

    def score(
        self,
        item: dict[str, Any],
        *,
        query: str,
        context: VisualRelevanceContext | None = None,
    ) -> VisualRelevanceResult:
        searchable = self._normalize(
            " ".join(str(item.get(key, "")) for key in ("alt", "description", "title"))
        )
        query_terms = self._tokens(query)
        matched_query = self._matched(query_terms, searchable)
        query_coverage = self._coverage(query_terms, matched_query)
        phrase_bonus = 0.20 if self._normalize(query) in searchable and query.strip() else 0.0
        base_relevance = min(1.0, query_coverage * 0.80 + phrase_bonus)

        if context is None:
            return VisualRelevanceResult(
                score=base_relevance,
                matched_terms=matched_query,
                reasons=(),
            )

        matched_context: list[str] = []
        context_score = 0.0
        context_weight = 0.0
        reasons: list[str] = []

        signals = (
            (context.entities, 0.30, "entity"),
            ((context.location,), 0.15, "location"),
            ((context.era,), 0.10, "era"),
            ((context.must_show), 0.30, "must_show"),
            ((context.action,), 0.05, "action"),
            ((context.visual_goal,), 0.10, "visual_goal"),
        )
        for values, weight, label in signals:
            terms = self._tokens(" ".join(value for value in values if value))
            if not terms:
                continue
            matched = self._matched(terms, searchable)
            coverage = self._coverage(terms, matched)
            context_score += coverage * weight
            context_weight += weight
            matched_context.extend(f"{label}:{term}" for term in matched)

            if label == "must_show" and coverage < 1.0:
                reasons.append("missing_must_show_terms")

        normalized_avoid = [self._normalize(value) for value in context.must_avoid if value.strip()]
        avoid_matches = tuple(value for value in normalized_avoid if value and value in searchable)
        if avoid_matches:
            reasons.append("must_avoid_match")

        contextual_relevance = context_score / context_weight if context_weight else 0.0
        relevance = min(1.0, base_relevance * 0.55 + contextual_relevance * 0.45)
        if "must_avoid_match" in reasons:
            relevance *= 0.25

        return VisualRelevanceResult(
            score=relevance,
            matched_terms=tuple(dict.fromkeys((*matched_query, *matched_context))),
            reasons=tuple(dict.fromkeys(reasons)),
        )

    @classmethod
    def _matched(cls, terms: tuple[str, ...], searchable: str) -> tuple[str, ...]:
        return tuple(term for term in terms if re.search(rf"\b{re.escape(term)}\b", searchable))

    @staticmethod
    def _coverage(terms: tuple[str, ...], matched: tuple[str, ...]) -> float:
        return len(matched) / len(terms) if terms else 0.0

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))

    @classmethod
    def _tokens(cls, value: str) -> tuple[str, ...]:
        stopwords = {
            "a",
            "an",
            "and",
            "at",
            "by",
            "for",
            "from",
            "in",
            "of",
            "on",
            "the",
            "to",
            "when",
            "with",
        }
        return tuple(token for token in cls._normalize(value).split() if token not in stopwords)
