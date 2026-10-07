from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from app.application.services.visual_semantic_verification import (
    VisualSemanticScore,
    VisualVerificationPolicy,
    VisualVerificationResult,
)


@dataclass(frozen=True, slots=True)
class VisualVerificationContext:
    """Semantic intent that a verifier must check against one asset."""

    entities: tuple[str, ...] = ()
    location: str = ""
    era: str = ""
    action: str = ""
    must_show: tuple[str, ...] = ()
    must_avoid: tuple[str, ...] = ()

    def searchable_intent(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (
                *self.entities,
                self.location,
                self.era,
                self.action,
                *self.must_show,
            )
            if value.strip()
        )


class VisualSemanticVerifier(Protocol):
    """Port for semantic verification providers."""

    def verify(
        self,
        item: dict[str, Any],
        *,
        context: VisualVerificationContext,
    ) -> VisualVerificationResult:
        """Verify whether an asset depicts the supplied visual intent."""


class DeterministicVisualSemanticVerifier:
    """Metadata-based semantic verifier used as a safe baseline provider.

    This provider never claims pixel-level understanding. It checks searchable
    asset metadata only, making its evidence deterministic and auditable.
    """

    name = "deterministic-metadata-v1"

    def __init__(
        self,
        *,
        policy: VisualVerificationPolicy | None = None,
    ) -> None:
        self._policy = policy or VisualVerificationPolicy()

    def verify(
        self,
        item: dict[str, Any],
        *,
        context: VisualVerificationContext,
    ) -> VisualVerificationResult:
        searchable = self._searchable(item)

        entity_match, entity_signals = self._group_match(context.entities, searchable)
        action_match, action_signals = self._group_match((context.action,), searchable)
        context_match, context_signals = self._group_match(
            (context.location, context.era),
            searchable,
        )
        must_show_match, must_show_signals = self._group_match(
            context.must_show,
            searchable,
        )

        avoided = tuple(
            value
            for value in context.must_avoid
            if self._normalize(value) and self._normalize(value) in searchable
        )
        must_avoid_compliance = 0.0 if avoided else 1.0

        overall = (
            entity_match * 0.30
            + action_match * 0.15
            + context_match * 0.20
            + must_show_match * 0.25
            + must_avoid_compliance * 0.10
        )
        score = VisualSemanticScore(
            entity_match=entity_match,
            action_match=action_match,
            context_match=context_match,
            must_show_match=must_show_match,
            must_avoid_compliance=must_avoid_compliance,
            overall=overall,
        )
        decision = self._policy.decide(score)

        matched = tuple(
            dict.fromkeys(
                (
                    *entity_signals,
                    *action_signals,
                    *context_signals,
                    *must_show_signals,
                )
            )
        )
        missing = tuple(
            value
            for value in (
                *context.entities,
                context.action,
                context.location,
                context.era,
                *context.must_show,
            )
            if value.strip() and self._normalize(value) not in searchable
        )
        violated = tuple(f"must_avoid:{value}" for value in avoided)

        return VisualVerificationResult(
            decision=decision,
            score=score,
            verifier=self.name,
            matched_signals=matched,
            missing_signals=missing,
            violated_constraints=violated,
        )

    @classmethod
    def _searchable(cls, item: dict[str, Any]) -> str:
        values = (
            item.get("alt"),
            item.get("description"),
            item.get("title"),
            item.get("tags"),
        )
        return cls._normalize(" ".join(cls._flatten(value) for value in values))

    @classmethod
    def _group_match(
        cls,
        values: tuple[str, ...],
        searchable: str,
    ) -> tuple[float, tuple[str, ...]]:
        normalized = tuple(cls._normalize(value) for value in values if value.strip())
        if not normalized:
            return 0.0, ()

        matched = tuple(value for value in normalized if value in searchable)
        return len(matched) / len(normalized), matched

    @staticmethod
    def _flatten(value: Any) -> str:
        if isinstance(value, (list, tuple, set)):
            return " ".join(str(part) for part in value)
        return str(value or "")

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))
