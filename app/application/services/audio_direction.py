from __future__ import annotations

from dataclasses import dataclass
import re


_SENTENCE_END_RE = re.compile(r"([.!?])(["')\]]?)(?=\s|$)")
_MULTI_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class AudioDirection:
    """Deterministic, provider-agnostic direction for one narration track."""

    tts_text: str
    sentence_count: int
    emphasis_terms: tuple[str, ...]
    energy: str

    def __post_init__(self) -> None:
        if not self.tts_text.strip():
            raise ValueError("tts_text must not be empty")
        if self.sentence_count < 1:
            raise ValueError("sentence_count must be positive")
        if self.energy not in {"low", "medium", "high"}:
            raise ValueError("energy must be low, medium, or high")


class AudioDirector:
    """Build one deterministic voice direction plan without another LLM call."""

    def plan(
        self,
        *,
        hook: str,
        body: str,
        cta: str | None = None,
    ) -> AudioDirection:
        parts = [self._normalize(hook)]
        if body.strip():
            parts.append(self._normalize(body))
        if cta and cta.strip():
            parts.append(self._normalize(cta))

        text = " ".join(part for part in parts if part)
        text = self._ensure_sentence_boundaries(text)
        sentences = self._split_sentences(text)
        emphasis_terms = self._extract_emphasis_terms(parts[0])

        if len(sentences) <= 2:
            energy = "high"
        elif len(sentences) <= 5:
            energy = "medium"
        else:
            energy = "low"

        return AudioDirection(
            tts_text=text,
            sentence_count=len(sentences),
            emphasis_terms=emphasis_terms,
            energy=energy,
        )

    @staticmethod
    def _normalize(value: str) -> str:
        text = value.replace("\u2014", ",").replace("\u2013", ",")
        text = _MULTI_SPACE_RE.sub(" ", text).strip()
        return text

    @staticmethod
    def _ensure_sentence_boundaries(text: str) -> str:
        if not text:
            return text
        text = _SENTENCE_END_RE.sub(r"\1\2 ", text)
        text = _MULTI_SPACE_RE.sub(" ", text).strip()
        if text[-1] not in ".!?":
            text += "."
        return text

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]

    @staticmethod
    def _extract_emphasis_terms(hook: str) -> tuple[str, ...]:
        words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9'’-]*", hook)
        candidates = [word for word in words if len(word) >= 5]
        return tuple(dict.fromkeys(candidates[:4]))
