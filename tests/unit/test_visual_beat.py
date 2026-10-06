import pytest

from app.application.services.scene_contract import build_scene_contract
from app.application.services.visual_beat import VisualBeatCompiler, VisualBeatTimeline


def _scene() -> object:
    return build_scene_contract(
        {
            "narration": "Rome grew powerful. Its armies conquered distant lands.",
            "visual_goal": "Show Roman expansion",
            "visual_query": "Roman Empire expansion map",
            "subject": "Roman Empire",
            "action": "expanding",
            "entities": ["Rome", "Roman Empire"],
            "location": "Mediterranean",
            "era": "ancient Rome",
            "must_show": ["Roman territory"],
            "must_avoid": ["modern borders"],
        }
    )


def test_compiler_preserves_scene_semantics_across_beats() -> None:
    timeline = VisualBeatCompiler().compile(
        _scene(), scene_index=2, scene_duration_seconds=8.0
    )

    assert len(timeline.beats) == 2
    for beat in timeline.beats:
        assert beat.scene_index == 2
        assert beat.visual_goal == "Show Roman expansion"
        assert beat.visual_query == "Roman Empire expansion map"
        assert beat.subject == "Roman Empire"
        assert beat.action == "expanding"
        assert beat.entities == ("Rome", "Roman Empire")
        assert beat.location == "Mediterranean"
        assert beat.era == "ancient Rome"
        assert beat.must_show == ("Roman territory",)
        assert beat.must_avoid == ("modern borders",)


def test_compiler_produces_contiguous_timeline_equal_to_scene_duration() -> None:
    timeline = VisualBeatCompiler().compile(
        _scene(), scene_index=0, scene_duration_seconds=10.0
    )

    assert timeline.beats[0].start_seconds == 0.0
    assert timeline.beats[0].end_seconds == pytest.approx(
        timeline.beats[1].start_seconds
    )
    assert timeline.total_duration_seconds == pytest.approx(10.0)
    assert timeline.beats[-1].end_seconds == pytest.approx(10.0)


def test_compiler_falls_back_to_one_beat_for_single_sentence() -> None:
    scene = build_scene_contract(
        {
            "narration": "The fleet arrived.",
            "visual_goal": "Show the fleet",
            "visual_query": "historical fleet harbor",
        }
    )

    timeline = VisualBeatCompiler().compile(
        scene, scene_index=1, scene_duration_seconds=6.0
    )

    assert len(timeline.beats) == 1
    assert timeline.beats[0].narration == "The fleet arrived."
    assert timeline.beats[0].duration_seconds == 6.0


def test_timeline_rejects_gaps_and_duration_mismatch() -> None:
    scene = _scene()
    compiler = VisualBeatCompiler()
    timeline = compiler.compile(scene, scene_index=0, scene_duration_seconds=8.0)

    with pytest.raises(ValueError, match="contiguous"):
        VisualBeatTimeline(
            scene_index=0,
            scene_duration_seconds=8.0,
            beats=(
                timeline.beats[0],
                timeline.beats[1].__class__(
                    **{
                        **timeline.beats[1].__dict__,
                        "start_seconds": timeline.beats[1].start_seconds + 0.5,
                    }
                ),
            ),
        )
