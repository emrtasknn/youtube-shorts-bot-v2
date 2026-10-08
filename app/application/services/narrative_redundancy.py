from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_WORD_RE = re.compile(r"\b[\w’'-]+\b", re.UNICODE)
_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)", re.UNICODE)
_MIN_COMPARISON_WORDS = 5


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower())).strip()


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _sentences(text: str) -> tuple[str, ...]:
    return tuple(
        sentence.strip() for sentence in _SENTENCE_RE.findall(text.strip()) if _normalize(sentence)
    )


def _similarity(left: str, right: str) -> float:
    left_normalized = _normalize(left)
    right_normalized = _normalize(right)
    if not left_normalized or not right_normalized:
        return 0.0
    sequence = SequenceMatcher(None, left_normalized, right_normalized).ratio()
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return sequence
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return max(sequence, jaccard)


@dataclass(frozen=True, slots=True)
class NarrativeRedundancyReport:
    passed: bool
    failures: tuple[str, ...]
    signals: tuple[str, ...]
    max_similarity: float
    compared_pairs: int

    def raise_if_failed(self) -> None:
        if not self.passed:
            raise ValueError("Narrative redundancy gate failed: " + "; ".join(self.failures))


class NarrativeRedundancyGate:
    """Conservative deterministic gate for repeated narrative claims."""

    high_similarity_threshold = 0.90
    hook_body_threshold = 0.82
    min_comparison_words = _MIN_COMPARISON_WORDS

    def evaluate(self, data: dict[str, object]) -> NarrativeRedundancyReport:
        failures: list[str] = []
        signals: list[str] = []

        hook = str(data.get("hook") or "").strip()
        body = str(data.get("body") or "").strip()
        scenes = data.get("scenes")

        body_sentences = _sentences(body)
        narrative_sentences: list[str] = []
        if hook:
            narrative_sentences.append(hook)
        narrative_sentences.extend(body_sentences)

        max_similarity = 0.0
        compared_pairs = 0

        normalized_seen: dict[str, int] = {}
        for index, sentence in enumerate(narrative_sentences):
            normalized = _normalize(sentence)
            if not normalized:
                continue
            if normalized in normalized_seen:
                duplicate_index = normalized_seen[normalized]
                failures.append(
                    f"exact duplicate narrative claim between items {duplicate_index} and {index}"
                )
                signals.append("exact_duplicate")
            else:
                normalized_seen[normalized] = index

        if hook and body_sentences:
            hook_words = _tokens(hook)
            first_body = body_sentences[0]
            first_body_words = _tokens(first_body)
            if (
                len(hook_words) >= self.min_comparison_words
                and len(first_body_words) >= self.min_comparison_words
            ):
                compared_pairs += 1
                similarity = _similarity(hook, first_body)
                max_similarity = max(max_similarity, similarity)
                if similarity >= self.hook_body_threshold:
                    failures.append(
                        f"hook repeats the first body claim (similarity {similarity:.2f})"
                    )
                    signals.append("hook_body_repetition")

        for index in range(1, len(narrative_sentences)):
            previous = narrative_sentences[index - 1]
            current = narrative_sentences[index]
            if (
                len(_tokens(previous)) < self.min_comparison_words
                or len(_tokens(current)) < self.min_comparison_words
            ):
                continue
            compared_pairs += 1
            similarity = _similarity(previous, current)
            max_similarity = max(max_similarity, similarity)
            if similarity >= self.high_similarity_threshold:
                failures.append(
                    "adjacent narrative sentences are highly similar "
                    f"(items {index - 1}/{index}, similarity {similarity:.2f})"
                )
                signals.append("adjacent_repetition")

        if isinstance(scenes, list):
            scene_sentences: list[str] = []
            for scene in scenes:
                if isinstance(scene, dict):
                    scene_narration = str(scene.get("narration") or "").strip()
                    scene_sentences.extend(_sentences(scene_narration))

            for index in range(1, len(scene_sentences)):
                previous = scene_sentences[index - 1]
                current = scene_sentences[index]
                if (
                    len(_tokens(previous)) < self.min_comparison_words
                    or len(_tokens(current)) < self.min_comparison_words
                ):
                    continue
                compared_pairs += 1
                similarity = _similarity(previous, current)
                max_similarity = max(max_similarity, similarity)
                if similarity >= self.high_similarity_threshold:
                    failures.append(
                        "adjacent scene narration is highly similar "
                        f"(items {index - 1}/{index}, similarity {similarity:.2f})"
                    )
                    signals.append("adjacent_scene_repetition")

        return NarrativeRedundancyReport(
            passed=not failures,
            failures=tuple(dict.fromkeys(failures)),
            signals=tuple(dict.fromkeys(signals)),
            max_similarity=round(max_similarity, 3),
            compared_pairs=compared_pairs,
        )
