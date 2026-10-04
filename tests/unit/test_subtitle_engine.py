from app.application.services.subtitle_engine import SubtitleEngine


def test_engine_breaks_on_punctuation_before_word_limit() -> None:
    cues = SubtitleEngine(max_words=6).build_cues(
        "The king arrived. The crowd went silent as everyone watched.",
        8.0,
    )

    assert [cue.text for cue in cues] == [
        "The king arrived.",
        "The crowd went silent as everyone",
        "watched.",
    ]


def test_engine_respects_word_and_character_limits() -> None:
    cues = SubtitleEngine(max_words=4, max_characters=24).build_cues(
        "One two three four five six seven eight",
        8.0,
    )

    assert all(len(cue.text.split()) <= 4 for cue in cues)
    assert all(len(cue.text) <= 24 for cue in cues)


def test_engine_allocates_monotonic_duration() -> None:
    cues = SubtitleEngine().build_cues(
        "Short words. A longer subtitle phrase should receive more time.",
        10.0,
    )

    assert cues[0].start_seconds == 0.0
    assert cues[-1].end_seconds == 10.0
    assert all(current.start_seconds < current.end_seconds for current in cues)
    assert all(
        left.end_seconds == right.start_seconds for left, right in zip(cues, cues[1:])
    )
    assert cues[-1].end_seconds - cues[-1].start_seconds > (
        cues[0].end_seconds - cues[0].start_seconds
    )


def test_engine_rejects_invalid_input() -> None:
    engine = SubtitleEngine()

    for text, duration in [("", 2.0), ("   ", 2.0), ("hello", 0.0)]:
        try:
            engine.build_cues(text, duration)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError")
