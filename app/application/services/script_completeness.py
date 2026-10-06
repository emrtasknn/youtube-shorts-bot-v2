from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_WORD_RE = re.compile(r"\b[\w’'-]+\b", re.UNICODE)
_SENTENCE_END_RE = re.compile(r"""[.!?]["'”’)]*$""")
_TRAILING_FRAGMENT_WORDS = {
    "and", "or", "but", "because", "that", "which", "who", "when", "while",
    "with", "from", "for", "to", "of", "in", "on", "as", "than", "until",
    "ve", "veya", "ama", "çünkü", "ki", "ile", "için", "olarak", "ancak",
    "fakat", "eğer", "iken", "kadar",
}
_STORY_PURPOSES = {"hook", "context", "event", "consequence", "payoff"}


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.strip())


def _normalized_words(text: str) -> set[str]:
    return {word.lower().strip(".,!?;:()[]{}\"'’”") for word in _words(text)}


def _ends_as_sentence(text: str) -> bool:
    return bool(_SENTENCE_END_RE.search(text.strip()))


@dataclass(frozen=True, slots=True)
class ScriptCompletenessReport:
    passed: bool
    failures: tuple[str, ...]
    body_word_count: int
    narration_word_count: int
    estimated_speech_seconds: float
    scene_duration_seconds: float

    def raise_if_failed(self) -> None:
        if not self.passed:
            raise ValueError(
                "Content completeness gate failed: " + "; ".join(self.failures)
            )


class ScriptCompletenessGate:
    """Deterministic pre-TTS gate preventing structurally incomplete stories."""

    words_per_second = 2.5
    min_scene_narration_ratio = 0.85
    min_scene_duration_ratio = 0.95

    def evaluate(self, data: dict[str, Any]) -> ScriptCompletenessReport:
        failures: list[str] = []
        hook = str(data.get("hook") or "").strip()
        body = str(data.get("body") or "").strip()
        cta = str(data.get("cta") or "").strip()
        scenes = data.get("scenes")
        target = float(data.get("duration_target") or 0)

        body_words = _words(body)
        all_narration = (
            " ".join(
                str(scene.get("narration") or "").strip()
                for scene in scenes
                if isinstance(scene, dict)
            )
            if isinstance(scenes, list)
            else ""
        )
        narration_words = _words(all_narration)
        total_tts_words = len(
            _words(" ".join(part for part in (hook, body, cta) if part))
        )
        estimated_seconds = total_tts_words / self.words_per_second
        scene_duration = (
            sum(
                float(scene.get("duration") or 0)
                for scene in scenes
                if isinstance(scene, dict)
            )
            if isinstance(scenes, list)
            else 0.0
        )

        if len(body_words) < 35:
            failures.append(
                f"body is too short ({len(body_words)} words; minimum 35)"
            )
        if not _ends_as_sentence(body):
            failures.append("body does not end with a complete sentence")
        if body_words and body_words[-1].lower().strip(
            ".,!?;:()[]{}\"'’”"
        ) in _TRAILING_FRAGMENT_WORDS:
            failures.append("body ends with a sentence fragment")
        if scenes is None or not isinstance(scenes, list) or len(scenes) < 3:
            failures.append("story needs at least 3 scenes")

        if body_words and len(narration_words) < len(body_words) * self.min_scene_narration_ratio:
            failures.append(
                f"scene narration covers only {len(narration_words)}/{len(body_words)} body words"
            )

        if scene_duration and estimated_seconds > scene_duration / self.min_scene_duration_ratio:
            failures.append(
                f"scene duration ({scene_duration:.1f}s) is too short for narration "
                f"({estimated_seconds:.1f}s estimated)"
            )

        if target and estimated_seconds < target * 0.70:
            failures.append(
                f"script is too short for target ({estimated_seconds:.1f}s estimated vs {target:.1f}s target)"
            )
        if target and estimated_seconds > target * 1.30:
            failures.append(
                f"script is too long for target ({estimated_seconds:.1f}s estimated vs {target:.1f}s target)"
            )

        if scenes:
            normalized_purposes = [
                str(scene.get("purpose") or "").strip().lower()
                for scene in scenes
                if isinstance(scene, dict)
            ]
            meaningful_purposes = [
                purpose
                for purpose in normalized_purposes
                if purpose in _STORY_PURPOSES
            ]
            if len(set(meaningful_purposes)) < 3:
                failures.append(
                    "storyboard needs at least 3 narrative beats "
                    "(hook/context/event/consequence/payoff)"
                )
            if meaningful_purposes and meaningful_purposes[0] != "hook":
                failures.append("first scene must be the hook beat")
            if meaningful_purposes and meaningful_purposes[-1] != "payoff":
                failures.append("last scene must be the payoff beat")

            for index, scene in enumerate(scenes):
                if not isinstance(scene, dict):
                    continue
                narration = str(scene.get("narration") or "").strip()
                if narration and not _ends_as_sentence(narration):
                    failures.append(f"scene {index} narration is incomplete")
                if narration:
                    last_word = _words(narration)[-1].lower().strip(
                        ".,!?;:()[]{}\"'’”"
                    )
                    if last_word in _TRAILING_FRAGMENT_WORDS:
                        failures.append(
                            f"scene {index} narration ends with a fragment"
                        )

        body_tokens = _normalized_words(body)
        narration_tokens = _normalized_words(all_narration)
        if body_tokens:
            token_coverage = len(body_tokens & narration_tokens) / len(body_tokens)
            if token_coverage < 0.60:
                failures.append(
                    f"storyboard vocabulary coverage is too low ({token_coverage:.0%})"
                )

        return ScriptCompletenessReport(
            passed=not failures,
            failures=tuple(dict.fromkeys(failures)),
            body_word_count=len(body_words),
            narration_word_count=len(narration_words),
            estimated_speech_seconds=estimated_seconds,
            scene_duration_seconds=scene_duration,
        )
