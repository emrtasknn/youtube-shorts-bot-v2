from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SceneTimingAllocator:
    """Allocates a target duration across scenes proportionally."""

    minimum_scene_duration: float = 0.5

    def __post_init__(self) -> None:
        if self.minimum_scene_duration <= 0:
            raise ValueError("minimum_scene_duration must be positive")

    def allocate(
        self,
        planned_durations: tuple[float, ...],
        target_duration: float,
    ) -> tuple[float, ...]:
        if not planned_durations:
            raise ValueError("At least one scene duration is required")
        if target_duration <= 0:
            raise ValueError("Target duration must be positive")
        if any(duration <= 0 for duration in planned_durations):
            raise ValueError("Scene durations must be positive")

        minimum_total = self.minimum_scene_duration * len(planned_durations)
        if target_duration < minimum_total:
            raise ValueError("Target duration is too short for the scene count")

        planned_total = sum(planned_durations)
        scale = target_duration / planned_total
        durations = tuple(duration * scale for duration in planned_durations)

        if any(duration < self.minimum_scene_duration for duration in durations):
            durations = self._allocate_with_minimums(
                planned_durations,
                target_duration,
            )

        return durations



    def normalize_for_narration(
        self,
        planned_durations: tuple[float, ...],
        narration_word_counts: tuple[int, ...],
        *,
        words_per_second: float = 2.5,
        safety_margin: float = 1.05,
    ) -> tuple[float, ...]:
        """Make storyboard timing safely cover each scene's narration.

        The LLM may provide approximate scene durations. Narration length is the
        deterministic source of truth, while original durations preserve relative
        visual pacing when spare time is available.
        """
        if len(planned_durations) != len(narration_word_counts):
            raise ValueError("Planned durations and narration counts must match")
        if not planned_durations:
            raise ValueError("At least one scene is required")
        if words_per_second <= 0:
            raise ValueError("words_per_second must be positive")
        if safety_margin < 1:
            raise ValueError("safety_margin must be at least 1")
        if any(duration <= 0 for duration in planned_durations):
            raise ValueError("Scene durations must be positive")
        if any(count < 0 for count in narration_word_counts):
            raise ValueError("Narration word counts must be non-negative")

        required = tuple(
            max(
                self.minimum_scene_duration,
                count / words_per_second * safety_margin,
            )
            for count in narration_word_counts
        )
        planned_total = sum(planned_durations)
        required_total = sum(required)
        target_total = max(planned_total, required_total)
        extra = target_total - required_total

        planned_weight = sum(planned_durations)
        return tuple(
            required_duration + extra * planned / planned_weight
            for required_duration, planned in zip(required, planned_durations, strict=True)
        )

    def _allocate_with_minimums(
        self,
        planned_durations: tuple[float, ...],
        target_duration: float,
    ) -> tuple[float, ...]:
        remaining_duration = target_duration
        remaining_weight = sum(planned_durations)
        result: list[float] = []

        for index, planned in enumerate(planned_durations):
            remaining_scenes = len(planned_durations) - index
            minimum_remaining = self.minimum_scene_duration * (remaining_scenes - 1)
            available = remaining_duration - minimum_remaining
            share = available * planned / remaining_weight
            duration = max(self.minimum_scene_duration, share)
            result.append(duration)
            remaining_duration -= duration
            remaining_weight -= planned

        return tuple(result)
