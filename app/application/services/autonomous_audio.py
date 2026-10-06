from __future__ import annotations

import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.application.services.audio_catalog import MusicCatalog, MusicTrack, SfxCatalog, SfxCue
from app.application.services.audio_direction import AudioDirection
from app.application.services.audio_quality import validate_generated_wav
from app.application.services.audio_synthesis import (
    ProceduralMusicGenerator,
    ProceduralSfxGenerator,
)


@dataclass(frozen=True, slots=True)
class AudioMixPlan:
    music: MusicTrack
    sfx: tuple[SfxCue, ...]
    background_audio_path: Path
    profile: str
    metadata: dict[str, object]


class AutonomousAudioPlanner:
    """Select and synthesize exactly one deterministic audio mix per run."""

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
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        output_dir.mkdir(parents=True, exist_ok=True)
        text = direction.tts_text
        music = self._music_catalog.select(text=text, energy=direction.energy)
        sfx = self._sfx_catalog.match(text)
        music_path = output_dir / f"music-{music.track_id}.wav"
        self._music_generator.generate(
            music, duration_seconds=duration_seconds, output_path=music_path
        )
        validate_generated_wav(music_path)
        sfx_paths: list[Path] = []
        for cue in sfx:
            path = output_dir / f"sfx-{cue.cue_id}.wav"
            self._sfx_generator.generate(cue, output_path=path)
            validate_generated_wav(path)
            sfx_paths.append(path)
        mixed_path = output_dir / "background-mix.wav"
        self._mix_assets(
            music_path,
            tuple(sfx_paths),
            duration_seconds=duration_seconds,
            output_path=mixed_path,
        )
        validate_generated_wav(mixed_path)
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
            "selection_policy": "deterministic_catalog_v1",
            "audio_variants_generated": 1,
            "sfx_density_limit": 2,
            "scene_count": len(scenes),
        }
        return AudioMixPlan(
            music=music,
            sfx=sfx,
            background_audio_path=mixed_path,
            profile=profile,
            metadata=metadata,
        )

    @staticmethod
    def _mix_assets(
        music_path: Path,
        sfx_paths: tuple[Path, ...],
        *,
        duration_seconds: float,
        output_path: Path,
    ) -> None:
        with wave.open(str(music_path), "rb") as music:
            params = music.getparams()
            frames = bytearray(music.readframes(music.getnframes()))
        if params.nchannels != 1 or params.sampwidth != 2:
            raise ValueError("M15 procedural audio expects mono 16-bit WAV")
        sample_count = min(
            len(frames) // 2,
            int(duration_seconds * params.framerate),
        )
        mixed = [
            struct.unpack_from("<h", frames, index * 2)[0] / 32767.0
            for index in range(sample_count)
        ]
        for cue_index, sfx_path in enumerate(sfx_paths):
            with wave.open(str(sfx_path), "rb") as sfx:
                sfx_frames = sfx.readframes(sfx.getnframes())
                sfx_rate = sfx.getframerate()
            start = min(
                sample_count - 1,
                int(
                    (cue_index + 1)
                    * duration_seconds
                    / (len(sfx_paths) + 1)
                    * params.framerate
                ),
            )
            if sfx_rate != params.framerate:
                raise ValueError("M15 procedural assets must use the same sample rate")
            for offset in range(
                min(len(sfx_frames) // 2, sample_count - start)
            ):
                value = struct.unpack_from("<h", sfx_frames, offset * 2)[0] / 32767.0
                mixed[start + offset] = max(
                    -1.0,
                    min(1.0, mixed[start + offset] + 0.28 * value),
                )
        pcm = b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767))
            for sample in mixed
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as output:
            output.setparams(params)
            output.writeframes(pcm)
