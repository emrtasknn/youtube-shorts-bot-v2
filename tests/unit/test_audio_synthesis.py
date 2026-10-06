from pathlib import Path
import wave

from app.application.services.audio_catalog import MusicCatalog, SfxCatalog
from app.application.services.audio_synthesis import ProceduralMusicGenerator, ProceduralSfxGenerator


def test_procedural_music_is_valid_wav(tmp_path: Path) -> None:
    track = MusicCatalog().select(text="history", energy="low")
    path = ProceduralMusicGenerator().generate(track, duration_seconds=1.0, output_path=tmp_path / "music.wav")
    with wave.open(str(path), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 24000


def test_procedural_sfx_is_valid_wav(tmp_path: Path) -> None:
    cue = SfxCatalog().match("suddenly an explosion")[0]
    path = ProceduralSfxGenerator().generate(cue, output_path=tmp_path / "sfx.wav")
    assert path.stat().st_size > 44
