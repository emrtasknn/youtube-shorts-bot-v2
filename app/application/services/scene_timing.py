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
