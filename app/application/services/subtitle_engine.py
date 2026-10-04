from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    start_seconds: float
    end_seconds: float
    text: str


class SubtitleEngine:
    """Deterministic subtitle segmentation and timing for short-form video."""

    def __init__(
        self,
        *,
        max_words: int = 6,
        max_characters: int = 34,
        punctuation_breaks: tuple[str, ...] = (".", "!", "?", ";", ":"),
    ) -> None:
        if max_words <= 0:
            raise ValueError("max_words must be positive")
        if max_characters <= 0:
            raise ValueError("max_characters must be positive")
        self._max_words = max_words
        self._max_characters = max_characters
        self._punctuation_breaks = punctuation_breaks

    def build_cues(self, text: str, duration_seconds: float) -> tuple[SubtitleCue, ...]:
        if not text.strip():
            raise ValueError("Subtitle text must not be empty")
        if duration_seconds <= 0:
            raise ValueError("Subtitle duration must be positive")

        chunks = self._segment(text)
        if not chunks:
            raise ValueError("Subtitle text must contain words")

        weights = [max(1, len(re.sub(r"\s+", "", chunk))) for chunk in chunks]
        total_weight = sum(weights)
        cues: list[SubtitleCue] = []
        cursor = 0.0
        for index, (chunk, weight) in enumerate(zip(chunks, weights, strict=True)):
            end = (
                duration_seconds
                if index == len(chunks) - 1
                else (cursor + duration_seconds * weight / total_weight)
            )
            cues.append(
                SubtitleCue(
                    start_seconds=cursor,
                    end_seconds=end,
                    text=chunk,
                )
            )
            cursor = end
        return tuple(cues)

    def _segment(self, text: str) -> list[str]:
        words = re.findall(r"\S+", text.strip())
        chunks: list[str] = []
        current: list[str] = []

        for word in words:
            candidate = " ".join((*current, word))
            should_break = current and (
                len(current) >= self._max_words or len(candidate) > self._max_characters
            )
            if should_break:
                chunks.append(" ".join(current))
                current = [word]
            else:
                current.append(word)

            if current and current[-1].endswith(self._punctuation_breaks):
                chunks.append(" ".join(current))
                current = []

        if current:
            chunks.append(" ".join(current))
        return chunks
