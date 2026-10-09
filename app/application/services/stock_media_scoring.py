from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.application.services.visual_relevance import VisualRelevanceContext, VisualRelevanceScorer


@dataclass(frozen=True, slots=True)
class StockMediaScore:
    score: float
    relevance: float
    orientation: float
    resolution: float
    duration: float
    duplicate_penalty: float
    eligible: bool
    reasons: tuple[str, ...]
    matched_terms: tuple[str, ...] = ()


class StockMediaScorer:
    def __init__(
        self,
        *,
        min_width: int = 1080,
        min_height: int = 1920,
        min_score: float = 0.60,
    ) -> None:
        self._min_width = min_width
        self._min_height = min_height
        self._min_score = min_score

    def score(
        self,
        item: dict[str, Any],
        *,
        query: str,
        used_provider_asset_ids: set[str] | None = None,
        min_duration: float = 2.0,
        max_duration: float = 60.0,
        min_relevance: float = 0.20,
        relevance_context: VisualRelevanceContext | None = None,
    ) -> StockMediaScore:
        reasons: list[str] = []
        relevance_result = VisualRelevanceScorer().score(
            item,
            query=query,
            context=relevance_context,
        )
        relevance = relevance_result.score
        matched_terms = relevance_result.matched_terms
        reasons.extend(relevance_result.reasons)

        width = self._as_number(item.get("width"))
        height = self._as_number(item.get("height"))
        portrait = height > width
        crop_allowed = item.get("portrait_crop_allowed") is True
        orientation = 1.0 if portrait else (0.65 if crop_allowed else 0.0)
        resolution = min(
            width / self._min_width if self._min_width else 1.0,
            height / self._min_height if self._min_height else 1.0,
        )
        resolution = max(0.0, min(1.0, resolution))

        duration = self._as_number(item.get("duration"))
        duration_score = 1.0
        if duration:
            if duration < min_duration or duration > max_duration:
                duration_score = 0.0
                reasons.append("duration_out_of_range")
        elif item.get("type") == "video":
            duration_score = 0.0
            reasons.append("missing_duration")

        provider_asset_id = str(item.get("id", ""))
        used_ids = used_provider_asset_ids or set()
        duplicate_penalty = 0.0
        if provider_asset_id and provider_asset_id in used_ids:
            duplicate_penalty = 1.0
            reasons.append("already_used")

        if relevance < min_relevance:
            reasons.append("low_relevance")
        if orientation == 0.0:
            reasons.append("not_portrait")
        elif not portrait:
            reasons.append("portrait_crop_required")
        if resolution < 0.50:
            reasons.append("low_resolution")

        score = (
            relevance * 0.45
            + orientation * 0.15
            + resolution * 0.25
            + duration_score * 0.15
            - duplicate_penalty
        )
        eligible = (
            score >= self._min_score
            and relevance >= min_relevance
            and orientation > 0.0
            and resolution >= 0.50
            and duplicate_penalty == 0.0
            and duration_score > 0.0
        )
        return StockMediaScore(
            score=max(0.0, min(1.0, score)),
            relevance=relevance,
            orientation=orientation,
            resolution=resolution,
            duration=duration_score,
            duplicate_penalty=duplicate_penalty,
            eligible=eligible,
            reasons=tuple(reasons),
            matched_terms=matched_terms,
        )

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

    @staticmethod
    def _as_number(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
