from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

HookType = Literal[
    "shocking_fact",
    "unanswered_question",
    "impossible_event",
    "curiosity_gap",
    "contradiction",
    "generic",
]


@dataclass(frozen=True, slots=True)
class HookEvaluation:
    text: str
    hook_type: HookType
    score: float
    word_count: int
    signals: tuple[str, ...]
    is_acceptable: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "hook_type": self.hook_type,
            "score": self.score,
            "word_count": self.word_count,
            "signals": list(self.signals),
            "is_acceptable": self.is_acceptable,
        }


class HookEngine:
    """Deterministic hook classification and quality scoring for Shorts."""

    _QUESTION_WORDS = {"why", "how", "what", "who", "where", "when"}
    _SHOCKING_TERMS = {
        "only",
        "never",
        "deadliest",
        "largest",
        "smallest",
        "youngest",
        "oldest",
        "survived",
        "record",
        "years",
    }
    _IMPOSSIBLE_TERMS = {
        "impossible",
        "vanished",
        "disappeared",
        "survived",
        "no one",
        "nobody",
        "couldn't",
        "could not",
        "never",
    }
    _CURIOSITY_TERMS = {
        "mystery",
        "secret",
        "hidden",
        "unknown",
        "what happened",
        "no one knows",
        "you won't believe",
    }
    _CONTRADICTION_TERMS = {
        "but",
        "yet",
        "however",
        "despite",
        "instead",
        "not",
        "wasn't",
        "was not",
        "weren't",
        "were not",
    }

    def __init__(self, *, min_words: int = 4, max_words: int = 18) -> None:
        if min_words <= 0:
            raise ValueError("min_words must be positive")
        if max_words < min_words:
            raise ValueError("max_words must be >= min_words")
        self._min_words = min_words
        self._max_words = max_words

    def evaluate(self, text: str) -> HookEvaluation:
        normalized = re.sub(r"\s+", " ", text.strip())
        if not normalized:
            raise ValueError("Hook text must not be empty")

        words = normalized.split()
        lowered = normalized.lower()
        signals: list[str] = []
        scores: dict[HookType, float] = {
            "shocking_fact": 0.0,
            "unanswered_question": 0.0,
            "impossible_event": 0.0,
            "curiosity_gap": 0.0,
            "contradiction": 0.0,
            "generic": 0.0,
        }

        if "?" in normalized or words and words[0].lower().rstrip(",") in self._QUESTION_WORDS:
            scores["unanswered_question"] += 0.55
            signals.append("question")

        if any(term in lowered for term in self._SHOCKING_TERMS):
            scores["shocking_fact"] += 0.45
            signals.append("shocking_fact_signal")

        if any(term in lowered for term in self._IMPOSSIBLE_TERMS):
            scores["impossible_event"] += 0.45
            signals.append("impossible_event_signal")

        if any(term in lowered for term in self._CURIOSITY_TERMS):
            scores["curiosity_gap"] += 0.55
            signals.append("curiosity_gap_signal")

        if any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in self._CONTRADICTION_TERMS):
            scores["contradiction"] += 0.45
            signals.append("contradiction_signal")

        word_count = len(words)
        if self._min_words <= word_count <= self._max_words:
            for hook_type in scores:
                scores[hook_type] += 0.15
            signals.append("short_form_length")
        elif word_count > self._max_words:
            signals.append("too_long")
        else:
            signals.append("too_short")

        best_type = max(scores, key=scores.__getitem__)
        score = min(1.0, scores[best_type])
        if best_type == "generic" or score < 0.55:
            best_type = "generic"
            score = min(score, 0.40)

        acceptable = best_type != "generic" and self._min_words <= word_count <= self._max_words

        return HookEvaluation(
            text=normalized,
            hook_type=best_type,
            score=round(score, 3),
            word_count=word_count,
            signals=tuple(signals),
            is_acceptable=acceptable,
        )

    def ensure_acceptable(self, text: str) -> HookEvaluation:
        evaluation = self.evaluate(text)
        if not evaluation.is_acceptable:
            raise ValueError(
                "Hook is too weak for the first 1-2 seconds: "
                f"type={evaluation.hook_type}, score={evaluation.score}"
            )
        return evaluation

    def fallback(self, topic: str) -> str:
        normalized = re.sub(r"\s+", " ", topic.strip())
        if not normalized:
            raise ValueError("Hook fallback topic must not be empty")
        return f"What really happened with {normalized}?"
