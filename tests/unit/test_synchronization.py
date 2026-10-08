from app.application.services.scene_contract import build_scene_contract
from app.application.services.visual_beat import VisualBeatCompiler
from app.application.services.synchronization import VisualNarrationSynchronizer


def _timelines() -> tuple:
    scene = build_scene_contract(
        {
            "narration": "Rome expanded across the Mediterranean. Its armies secured key ports.",
            "visual_goal": "Show Roman expansion",
            "visual_query": "Roman Empire Mediterranean expansion",
            "purpose": "event",
            "subject": "Roman Empire",
            "action": "expanding",
            "entities": ["Rome"],
            "location": "Mediterranean",
            "era": "ancient Rome",
            "visual_intent": "territorial expansion",
            "visual_style": "documentary",
            "must_show": ["Roman territory"],
            "must_avoid": ["modern borders"],
        }
    )
    return (VisualBeatCompiler().compile(scene, scene_index=0, scene_duration_seconds=6.0),)


def test_synchronizer_builds_one_contiguous_timeline() -> None:
    result = VisualNarrationSynchronizer().synchronize(
        _timelines(),
        (8.0,),
        "Rome expanded across the Mediterranean. Its armies secured key ports.",
        total_audio_duration=8.0,
    )
    assert result.passed
    assert result.total_duration_seconds == 8.0
    assert result.scenes[0].duration_seconds == 8.0
    assert result.scenes[0].beats[-1].end_seconds == 8.0
    assert result.subtitle_cues[-1].end_seconds == 8.0


def test_major_scene_drift_is_detected() -> None:
    result = VisualNarrationSynchronizer().synchronize(
        _timelines(),
        (8.0,),
        "Rome expanded across the Mediterranean. Its armies secured key ports.",
        total_audio_duration=8.0,
    )
    assert not result.passed
    assert any(issue.code == "major_scene_duration_drift" for issue in result.issues)


def test_small_scene_drift_is_reconciled() -> None:
    result = VisualNarrationSynchronizer().synchronize(
        _timelines(),
        (6.5,),
        "Rome expanded across the Mediterranean. Its armies secured key ports.",
        total_audio_duration=6.5,
    )
    assert result.passed
    assert result.max_scene_drift_seconds == 0.5


def test_subtitles_remain_inside_unified_timeline() -> None:
    result = VisualNarrationSynchronizer().synchronize(
        _timelines(),
        (6.0,),
        "Rome expanded across the Mediterranean. Its armies secured key ports.",
        total_audio_duration=6.0,
    )
    assert all(cue.start_seconds >= 0 for cue in result.subtitle_cues)
    assert result.subtitle_cues[-1].end_seconds == result.total_duration_seconds


def test_invalid_duration_contract_is_rejected() -> None:
    synchronizer = VisualNarrationSynchronizer()
    try:
        synchronizer.synchronize(
            _timelines(),
            (6.0,),
            "Rome expanded.",
            total_audio_duration=5.0,
        )
    except ValueError as exc:
        assert "complete audio duration" in str(exc)
    else:
        raise AssertionError("Expected invalid duration contract to be rejected")


def test_flatten_and_render_durations_follow_one_timeline() -> None:
    result = VisualNarrationSynchronizer().synchronize(
        _timelines(),
        (6.0,),
        "Rome expanded across the Mediterranean. Its armies secured key ports.",
        total_audio_duration=6.0,
    )
    assert len(VisualNarrationSynchronizer.flatten_beats(result)) == 2
    assert VisualNarrationSynchronizer.build_render_durations(result) == (6.0,)
