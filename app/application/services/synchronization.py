from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.application.services.subtitle_engine import SubtitleCue, SubtitleEngine
from app.application.services.visual_beat import VisualBeatTimeline


@dataclass(frozen=True, slots=True)
class SynchronizedBeat:
    scene_index: int
    beat_index: int
    start_seconds: float
    duration_seconds: float
    end_seconds: float
    narration: str

    @classmethod
    def from_beat(
        cls,
        beat: object,
        *,
        start_seconds: float,
        duration_seconds: float,
    ) -> SynchronizedBeat:
        return cls(
            scene_index=beat.scene_index,
            beat_index=beat.beat_index,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            end_seconds=start_seconds + duration_seconds,
            narration=beat.narration,
        )


@dataclass(frozen=True, slots=True)
class SynchronizedSceneTimeline:
    scene_index: int
    start_seconds: float
    duration_seconds: float
    beats: tuple[SynchronizedBeat, ...]

    def __post_init__(self) -> None:
        if self.duration_seconds <= 0:
            raise ValueError("Synchronized scene duration must be positive")
        if not self.beats:
            raise ValueError("Synchronized scene needs at least one beat")
        expected = self.start_seconds
        for index, beat in enumerate(self.beats):
            if beat.beat_index != index:
                raise ValueError("Synchronized beat indexes must be contiguous")
            if abs(beat.start_seconds - expected) > 1e-6:
                raise ValueError("Synchronized beats must be contiguous")
            expected = beat.end_seconds
        if abs(expected - (self.start_seconds + self.duration_seconds)) > 1e-6:
            raise ValueError("Synchronized beats must cover the scene duration")


@dataclass(frozen=True, slots=True)
class SynchronizationIssue:
    code: str
    severity: str
    drift_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class UnifiedTimeline:
    scenes: tuple[SynchronizedSceneTimeline, ...]
    subtitle_cues: tuple[SubtitleCue, ...]
    total_duration_seconds: float
    max_scene_drift_seconds: float
    issues: tuple[SynchronizationIssue, ...]

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


class VisualNarrationSynchronizer:
    """Builds the single authoritative render timeline after actual TTS timing is known."""

    def __init__(
        self,
        *,
        major_drift_seconds: float = 1.5,
        major_drift_ratio: float = 0.20,
        subtitle_engine: SubtitleEngine | None = None,
    ) -> None:
        if major_drift_seconds <= 0 or major_drift_ratio <= 0:
            raise ValueError("Synchronization thresholds must be positive")
        self._major_drift_seconds = major_drift_seconds
        self._major_drift_ratio = major_drift_ratio
        self._subtitle_engine = subtitle_engine or SubtitleEngine()

    def synchronize(
        self,
        timelines: Sequence[VisualBeatTimeline],
        actual_scene_durations: Sequence[float],
        subtitle_text: str,
        *,
        total_audio_duration: float,
    ) -> UnifiedTimeline:
        if not timelines:
            raise ValueError("At least one visual timeline is required")
        if len(timelines) != len(actual_scene_durations):
            raise ValueError("Timeline and scene duration counts must match")
        if total_audio_duration <= 0:
            raise ValueError("Audio duration must be positive")
        if any(duration <= 0 for duration in actual_scene_durations):
            raise ValueError("Actual scene durations must be positive")
        if abs(sum(actual_scene_durations) - total_audio_duration) > 1e-4:
            raise ValueError("Scene durations must cover the complete audio duration")

        scenes: list[SynchronizedSceneTimeline] = []
        issues: list[SynchronizationIssue] = []
        scene_cursor = 0.0
        max_drift = 0.0

        for timeline, target_duration in zip(timelines, actual_scene_durations, strict=True):
            planned = timeline.scene_duration_seconds
            drift = target_duration - planned
            max_drift = max(max_drift, abs(drift))
            ratio = abs(drift) / planned
            if abs(drift) > self._major_drift_seconds or ratio > self._major_drift_ratio:
                issues.append(
                    SynchronizationIssue(
                        code="major_scene_duration_drift",
                        severity="error",
                        drift_seconds=drift,
                    )
                )

            scale = target_duration / planned
            cursor = scene_cursor
            beats: list[SynchronizedBeat] = []
            for beat_index, beat in enumerate(timeline.beats):
                duration = beat.duration_seconds * scale
                if beat_index == len(timeline.beats) - 1:
                    duration = target_duration - sum(item.duration_seconds for item in beats)
                beats.append(
                    SynchronizedBeat.from_beat(
                        beat,
                        start_seconds=cursor,
                        duration_seconds=duration,
                    )
                )
                cursor += duration

            scenes.append(
                SynchronizedSceneTimeline(
                    scene_index=timeline.scene_index,
                    start_seconds=scene_cursor,
                    duration_seconds=target_duration,
                    beats=tuple(beats),
                )
            )
            scene_cursor += target_duration

        subtitle_cues = self._subtitle_engine.build_cues(
            subtitle_text,
            total_audio_duration,
        )
        self._validate_caption_coverage(subtitle_cues, scenes, issues)
        if abs(scene_cursor - total_audio_duration) > 1e-4:
            issues.append(
                SynchronizationIssue(
                    code="timeline_audio_end_drift",
                    severity="error",
                    drift_seconds=scene_cursor - total_audio_duration,
                )
            )

        return UnifiedTimeline(
            scenes=tuple(scenes),
            subtitle_cues=subtitle_cues,
            total_duration_seconds=total_audio_duration,
            max_scene_drift_seconds=max_drift,
            issues=tuple(issues),
        )

    @staticmethod
    def _validate_caption_coverage(
        cues: tuple[SubtitleCue, ...],
        scenes: Sequence[SynchronizedSceneTimeline],
        issues: list[SynchronizationIssue],
    ) -> None:
        if not cues:
            issues.append(
                SynchronizationIssue(code="missing_caption_cues", severity="error")
            )
            return
        for cue in cues:
            if cue.start_seconds < 0 or cue.end_seconds <= cue.start_seconds:
                issues.append(
                    SynchronizationIssue(code="invalid_caption_timing", severity="error")
                )
                continue
            if not any(
                cue.start_seconds < scene.start_seconds + scene.duration_seconds
                and cue.end_seconds > scene.start_seconds
                for scene in scenes
            ):
                issues.append(
                    SynchronizationIssue(
                        code="caption_outside_visual_timeline",
                        severity="error",
                    )
                )

    @staticmethod
    def build_render_durations(timeline: UnifiedTimeline) -> tuple[float, ...]:
        return tuple(scene.duration_seconds for scene in timeline.scenes)

    @staticmethod
    def flatten_beats(timeline: UnifiedTimeline) -> tuple[SynchronizedBeat, ...]:
        return tuple(beat for scene in timeline.scenes for beat in scene.beats)
