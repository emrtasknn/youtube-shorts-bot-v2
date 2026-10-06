from app.application.services.audio_direction import AudioDirector


def test_audio_director_creates_one_normalized_tts_track() -> None:
    plan = AudioDirector().plan(
        hook="The tank exploded—without warning",
        body="Thousands of liters flooded the streets",
        cta="Would you have survived?",
    )

    assert plan.tts_text == (
        "The tank exploded, without warning. "
        "Thousands of liters flooded the streets. "
        "Would you have survived?"
    )
    assert plan.sentence_count == 3
    assert plan.energy == "medium"


def test_audio_director_is_deterministic_and_extracts_hook_terms() -> None:
    director = AudioDirector()
    first = director.plan(hook="A shocking discovery", body="The evidence changed everything")
    second = director.plan(hook="A shocking discovery", body="The evidence changed everything")

    assert first == second
    assert first.emphasis_terms == ("shocking", "discovery")


def test_audio_director_adds_final_sentence_boundary() -> None:
    plan = AudioDirector().plan(hook="Watch this", body="It changed history")

    assert plan.tts_text.endswith(".")
    assert plan.sentence_count == 2
