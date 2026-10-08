from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubtitleWordTiming:
    word: str
    start_seconds: float
    end_seconds: float
    emphasized: bool = False


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    start_seconds: float
    end_seconds: float
    text: str
    words: tuple[SubtitleWordTiming, ...] = ()


@dataclass(frozen=True, slots=True)
class SubtitleSafeArea:
    width: int = 1080
    height: int = 1920
    margin_left: int = 80
    margin_right: int = 80
    margin_top: int = 300
    margin_bottom: int = 390
    max_characters: int = 34

    def validate(self) -> None:
        if (
            min(
                self.width,
                self.height,
                self.margin_left,
                self.margin_right,
                self.margin_top,
                self.margin_bottom,
                self.max_characters,
            )
            <= 0
        ):
            raise ValueError("Subtitle safe-area dimensions must be positive")
        if self.margin_left + self.margin_right >= self.width:
            raise ValueError("Subtitle horizontal margins leave no usable width")
        if self.margin_top + self.margin_bottom >= self.height:
            raise ValueError("Subtitle vertical margins leave no usable height")


class SubtitleEngine:
    """Deterministic, narration-aligned subtitle timing for Shorts."""

    _STOPWORDS = frozenset(
        {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "but",
            "by",
            "for",
            "from",
            "has",
            "have",
            "in",
            "is",
            "it",
            "of",
            "on",
            "or",
            "that",
            "the",
            "their",
            "this",
            "to",
            "was",
            "were",
            "with",
        }
    )

    def __init__(
        self,
        *,
        max_words: int = 6,
        max_characters: int = 34,
        punctuation_breaks: tuple[str, ...] = (".", "!", "?", ";", ":"),
        safe_area: SubtitleSafeArea | None = None,
    ) -> None:
        if max_words <= 0:
            raise ValueError("max_words must be positive")
        if max_characters <= 0:
            raise ValueError("max_characters must be positive")
        self._max_words = max_words
        self._max_characters = max_characters
        self._punctuation_breaks = punctuation_breaks
        self._safe_area = safe_area or SubtitleSafeArea(max_characters=max_characters)
        self._safe_area.validate()

    @property
    def safe_area(self) -> SubtitleSafeArea:
        return self._safe_area

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
                else cursor + duration_seconds * weight / total_weight
            )
            words = self._word_timings(chunk, cursor, end)
            cues.append(
                SubtitleCue(
                    start_seconds=cursor,
                    end_seconds=end,
                    text=chunk,
                    words=words,
                )
            )
            cursor = end
        return tuple(cues)

    def build_word_timestamps(
        self, text: str, duration_seconds: float
    ) -> tuple[SubtitleWordTiming, ...]:
        return tuple(word for cue in self.build_cues(text, duration_seconds) for word in cue.words)

    def _word_timings(
        self, chunk: str, start_seconds: float, end_seconds: float
    ) -> tuple[SubtitleWordTiming, ...]:
        words = re.findall(r"\S+", chunk)
        if not words:
            return ()
        weights = [max(1, len(re.sub(r"\W", "", word))) for word in words]
        total_weight = sum(weights)
        cursor = start_seconds
        result: list[SubtitleWordTiming] = []
        emphasized_indexes = self._emphasis_indexes(words)
        for index, (word, weight) in enumerate(zip(words, weights, strict=True)):
            end = (
                end_seconds
                if index == len(words) - 1
                else cursor + (end_seconds - start_seconds) * weight / total_weight
            )
            result.append(
                SubtitleWordTiming(
                    word=word,
                    start_seconds=cursor,
                    end_seconds=end,
                    emphasized=index in emphasized_indexes,
                )
            )
            cursor = end
        return tuple(result)

    def _emphasis_indexes(self, words: list[str]) -> frozenset[int]:
        candidates = [
            (index, re.sub(r"\W", "", word).lower())
            for index, word in enumerate(words)
            if re.sub(r"\W", "", word).lower() not in self._STOPWORDS
        ]
        candidates.sort(key=lambda item: (-len(item[1]), item[0]))
        return frozenset(index for index, _ in candidates[:2])

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
