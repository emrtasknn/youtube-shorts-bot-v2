from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.application.services.audio_catalog import MusicCatalog, MusicTrack, SfxCatalog, SfxCue
from app.application.services.audio_direction import AudioDirection
from app.application.services.audio_synthesis import ProceduralMusicGenerator, ProceduralSfxGenerator
from app.application.services.audio_quality import validate_generated_wav


@dataclass(frozen=True, slots=True)
class AudioMixPlan:
    music: MusicTrack
    sfx: tuple[SfxCue, ...]
    background_audio_path: Path
    profile: str
    metadata: dict[str, object]


class AutonomousAudioPlanner:
    """Select and synthesize exactly one deterministic audio bed per run."""

    def __init__(self) -> None:
        self._music_catalog = MusicCatalog()
        self._sfx_catalog = SfxCatalog()
        self._music_generator = ProceduralMusicGenerator()
        self._sfx_generator = ProceduralSfxGenerator()

    def build(
        self,
        *,
        run_id: UUID,
        direction: AudioDirection,
        scenes: tuple[dict[str, object], ...],
        duration_seconds: float,
        output_dir: Path,
    ) -> AudioMixPlan:
        output_dir.mkdir(parents=True, exist_ok=True)
        text = direction.tts_text
        music = self._music_catalog.select(text=text, energy=direction.energy)
        sfx = self._sfx_catalog.match(text)
        music_path = output_dir / f"music-{music.track_id}.wav"
        self._music_generator.generate(music, duration_seconds=duration_seconds, output_path=music_path)
        validate_generated_wav(music_path)

        # The current renderer consumes one background track. M15 therefore
        # keeps SFX bounded and folds their identity into the audio profile.
        # SFX synthesis remains traceable; the mix itself stays one-track.
        sfx_paths: list[Path] = []
        for cue in sfx:
            path = output_dir / f"sfx-{cue.cue_id}.wav"
            self._sfx_generator.generate(cue, output_path=path)
            validate_generated_wav(path)
            sfx_paths.append(path)

        profile = f"m15:{music.track_id}:sfx={','.join(cue.cue_id for cue in sfx) or 'none'}"
        metadata: dict[str, object] = {
            "profile_version": "m15-v1",
            "run_id": str(run_id),
            "music": {
                "track_id": music.track_id,
                "mood": music.mood,
                "energy": music.energy,
                "bpm": music.bpm,
                "instrumental": music.instrumental,
                "source": music.source,
                "license": music.license,
            },
            "sfx": [
                {
                    "cue_id": cue.cue_id,
                    "kind": cue.kind,
                    "source": cue.source,
                    "license": cue.license,
                }
                for cue in sfx
            ],
            "sfx_paths": [str(path) for path in sfx_paths],
            "selection_policy": "deterministic_catalog_v1",
            "audio_variants_generated": 1,
        }
        return AudioMixPlan(
            music=music,
            sfx=sfx,
            background_audio_path=music_path,
            profile=profile,
            metadata=metadata,
        )
