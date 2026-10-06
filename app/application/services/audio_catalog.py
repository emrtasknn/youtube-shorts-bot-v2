from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MusicTrack:
    track_id: str
    mood: str
    energy: str
    bpm: int
    instrumental: bool
    source: str = "procedural"
    license: str = "original-procedural"
    version: str = "m15-v1"


@dataclass(frozen=True, slots=True)
class SfxCue:
    cue_id: str
    kind: str
    trigger_terms: tuple[str, ...]
    duration_seconds: float = 0.35
    source: str = "procedural"
    license: str = "original-procedural"


class MusicCatalog:
    """Small deterministic catalog of original procedural music profiles."""

    _tracks = (
        MusicTrack("pulse-mystery-120", "mystery", "medium", 120, True),
        MusicTrack("dark-tension-132", "tension", "high", 132, True),
        MusicTrack("cinematic-drive-108", "cinematic", "medium", 108, True),
        MusicTrack("calm-history-92", "documentary", "low", 92, True),
    )

    def select(self, *, text: str, energy: str) -> MusicTrack:
        lowered = text.lower()
        if any(term in lowered for term in ("murder", "disaster", "flood", "explosion", "war", "death")):
            mood = "tension"
        elif any(term in lowered for term in ("secret", "mystery", "unknown", "strange", "mysterious")):
            mood = "mystery"
        elif energy == "low":
            mood = "documentary"
        else:
            mood = "cinematic"
        candidates = [track for track in self._tracks if track.mood == mood]
        return sorted(candidates, key=lambda track: (abs(self._energy_rank(track.energy) - self._energy_rank(energy)), track.track_id))[0]

    @staticmethod
    def _energy_rank(value: str) -> int:
        return {"low": 0, "medium": 1, "high": 2}[value]


class SfxCatalog:
    _cues = (
        SfxCue("impact", "impact", ("explod", "crash", "collapse", "hit", "struck")),
        SfxCue("whoosh", "whoosh", ("suddenly", "rushed", "flew", "revealed", "transition")),
        SfxCue("alarm", "alarm", ("danger", "warning", "emergency")),
        SfxCue("heartbeat", "heartbeat", ("panic", "terrified", "fear", "survive")),
    )

    def match(self, text: str) -> tuple[SfxCue, ...]:
        lowered = text.lower()
        matches = [
            cue
            for cue in self._cues
            if any(term in lowered for term in cue.trigger_terms)
        ]
        return tuple(matches[:2])
