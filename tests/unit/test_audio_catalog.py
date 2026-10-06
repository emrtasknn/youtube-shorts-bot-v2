from app.application.services.audio_catalog import MusicCatalog, SfxCatalog


def test_music_selection_is_deterministic_and_traceable() -> None:
    first = MusicCatalog().select(text="A terrifying flood destroyed the city", energy="high")
    second = MusicCatalog().select(text="A terrifying flood destroyed the city", energy="high")

    assert first == second
    assert first.license == "original-procedural"
    assert first.instrumental


def test_sfx_selection_is_bounded() -> None:
    cues = SfxCatalog().match("Suddenly the tank exploded and the crowd panicked.")
    assert len(cues) <= 2
    assert {cue.cue_id for cue in cues} == {"impact", "whoosh", "heartbeat"} & {
        cue.cue_id for cue in cues
    }
