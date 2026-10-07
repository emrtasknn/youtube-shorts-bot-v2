from __future__ import annotations

from dataclasses import dataclass

from app.application.services.scene_contract import SceneContract
from app.application.services.scene_timing import SceneTimingAllocator


@dataclass(frozen=True, slots=True)
class VisualBeat:
    """A timed visual unit derived from one scene contract."""

    scene_index: int
    beat_index: int
    start_seconds: float
    duration_seconds: float
    narration: str
    visual_goal: str
    visual_query: str
    purpose: str
    subject: str
    action: str
    entities: tuple[str, ...]
    location: str
    era: str
    visual_intent: str
    visual_style: str
    must_show: tuple[str, ...]
    must_avoid: tuple[str, ...]

    @property
    def end_seconds(self) -> float:
        return self.start_seconds + self.duration_seconds


@dataclass(frozen=True, slots=True)
class VisualBeatTimeline:
    """Compatibility boundary between scene contracts and visual retrieval."""

    scene_index: int
    scene_duration_seconds: float
    beats: tuple[VisualBeat, ...]

    def __post_init__(self) -> None:
        if self.scene_duration_seconds <= 0:
            raise ValueError("Scene duration must be positive")
        if not self.beats:
            raise ValueError("A visual beat timeline needs at least one beat")

        expected_start = 0.0
        for index, beat in enumerate(self.beats):
            if beat.scene_index != self.scene_index:
                raise ValueError("All beats must belong to the same scene")
            if beat.beat_index != index:
                raise ValueError("Beat indexes must be contiguous")
            if beat.start_seconds < 0:
                raise ValueError("Beat start must not be negative")
            if beat.duration_seconds <= 0:
                raise ValueError("Beat duration must be positive")
            if abs(beat.start_seconds - expected_start) > 1e-6:
                raise ValueError("Visual beats must be contiguous")
            expected_start = beat.end_seconds

        if abs(expected_start - self.scene_duration_seconds) > 1e-6:
            raise ValueError("Visual beat duration must equal scene duration")

    @property
    def total_duration_seconds(self) -> float:
        return sum(beat.duration_seconds for beat in self.beats)


class VisualBeatCompiler:
    """Compiles scene contracts into deterministic, retrieval-safe visual beats.

    This is intentionally a small transformation layer. It does not perform
    retrieval, rendering, or orchestration. If pacing cannot safely produce
    multiple beats, the original scene becomes one compatible fallback beat.
    """

    def __init__(
        self,
        timing_allocator: SceneTimingAllocator | None = None,
    ) -> None:
        self._timing_allocator = timing_allocator or SceneTimingAllocator()

    def compile(
        self,
        scene: SceneContract,
        *,
        scene_index: int,
        scene_duration_seconds: float,
    ) -> VisualBeatTimeline:
        if scene_index < 0:
            raise ValueError("Scene index must not be negative")
        if scene_duration_seconds <= 0:
            raise ValueError("Scene duration must be positive")

        parts = self._split_narration(scene.narration)
        if len(parts) <= 1:
            return self._fallback(scene, scene_index, scene_duration_seconds)

        try:
            durations = self._timing_allocator.normalize_for_narration(
                self._planned_durations(scene_duration_seconds, len(parts)),
                tuple(self._word_count(part) for part in parts),
            )
        except (ValueError, ZeroDivisionError):
            return self._fallback(scene, scene_index, scene_duration_seconds)

        beats: list[VisualBeat] = []
        start = 0.0
        for beat_index, (narration, duration) in enumerate(zip(parts, durations, strict=True)):
            beats.append(
                self._build_beat(
                    scene,
                    scene_index=scene_index,
                    beat_index=beat_index,
                    start_seconds=start,
                    duration_seconds=duration,
                    narration=narration,
                )
            )
            start += duration

        return VisualBeatTimeline(
            scene_index=scene_index,
            scene_duration_seconds=scene_duration_seconds,
            beats=tuple(beats),
        )

    def _fallback(
        self,
        scene: SceneContract,
        scene_index: int,
        scene_duration_seconds: float,
    ) -> VisualBeatTimeline:
        return VisualBeatTimeline(
            scene_index=scene_index,
            scene_duration_seconds=scene_duration_seconds,
            beats=(
                self._build_beat(
                    scene,
                    scene_index=scene_index,
                    beat_index=0,
                    start_seconds=0.0,
                    duration_seconds=scene_duration_seconds,
                    narration=scene.narration,
                ),
            ),
        )

    @staticmethod
    def _build_beat(
        scene: SceneContract,
        *,
        scene_index: int,
        beat_index: int,
        start_seconds: float,
        duration_seconds: float,
        narration: str,
    ) -> VisualBeat:
        return VisualBeat(
            scene_index=scene_index,
            beat_index=beat_index,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            narration=narration,
            visual_goal=scene.visual_goal,
            visual_query=scene.visual_query,
            purpose=scene.purpose,
            subject=scene.subject,
            action=scene.action,
            entities=scene.entities,
            location=scene.location,
            era=scene.era,
            visual_intent=scene.visual_intent,
            visual_style=scene.visual_style,
            must_show=scene.must_show,
            must_avoid=scene.must_avoid,
        )

    @staticmethod
    def _split_narration(narration: str) -> tuple[str, ...]:
        parts = tuple(
            part.strip()
            for part in narration.replace("!", ".").replace("?", ".").split(".")
            if part.strip()
        )
        return parts

    @staticmethod
    def _word_count(text: str) -> int:
        return len(text.split())

    @staticmethod
    def _planned_durations(
        scene_duration_seconds: float,
        count: int,
    ) -> tuple[float, ...]:
        return (scene_duration_seconds / count,) * count
