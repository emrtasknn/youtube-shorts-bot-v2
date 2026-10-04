import json

import pytest

from app.application.services.audio_ducking import AudioDucking
from app.application.services.custom_short_support import parse_script, validate_output
from app.application.services.hook_engine import HookEngine
from app.application.services.scene_contract import build_scene_contract
from app.application.services.scene_timing import SceneTimingAllocator
from app.application.services.video_quality import VideoQualityGate, VideoQualityExpectation


def _script_payload() -> dict[str, object]:
    return {
        "hook": "What really happened in Rome?",
        "body": "A short historical explanation.",
        "duration_target": 30,
        "event_memory": {
            "canonical_title": "Example Historical Event",
            "aliases": ["Example Event"],
            "date": "1900-01-01",
            "location": "Rome",
            "entities": ["Example Event"],
            "event_summary": "A historical event.",
            "core_facts": ["Fact one"],
            "claims": ["Claim one"],
            "sources": ["Source one"],
            "status": "NEW_EVENT",
        },
        "scenes": [
            {
                "duration": 10,
                "narration": "The event began.",
                "visual_goal": "Historical event beginning",
                "visual_query": "historical event Rome",
            }
        ]
        * 3,
    }


def test_script_regression_preserves_event_memory_and_scene_defaults() -> None:
    result = parse_script(json.dumps(_script_payload()))

    assert result["event_memory"]["canonical_title"] == "Example Historical Event"
    assert result["scenes"][0]["purpose"] == "support_narration"
    assert result["scenes"][0]["subject"] == "historical event Rome"


def test_scene_contract_rejects_missing_required_visual_contract() -> None:
    with pytest.raises(ValueError, match="visual_query"):
        build_scene_contract(
            {
                "narration": "Something happened.",
                "visual_goal": "Historical event",
            }
        )


def test_hook_regression_rejects_generic_and_accepts_question() -> None:
    engine = HookEngine()

    assert engine.evaluate("A short history video").is_acceptable is False
    assert engine.evaluate("What really happened in Rome?").is_acceptable is True


def test_audio_ducking_regression_keeps_sidechain_graph() -> None:
    command = AudioDucking().build_filter()

    assert "sidechaincompress" in command
    assert "amix=inputs=2" in command
    assert "[aout]" in command


def test_scene_timing_regression_preserves_total_duration() -> None:
    durations = SceneTimingAllocator().allocate((6.0, 6.0, 6.0), 30.0)

    assert sum(durations) == pytest.approx(30.0)
    assert durations[0] == pytest.approx(durations[1])
    assert durations[1] == pytest.approx(durations[2])


def test_quality_gate_regression_rejects_wrong_vertical_output() -> None:
    report = VideoQualityGate(
        VideoQualityExpectation(width=1080, height=1920, fps=30.0)
    ).evaluate(
        duration_seconds=30.0,
        width=1920,
        height=1080,
        fps=30.0,
        has_audio=True,
        subtitle_path=None,
        expected_duration=30.0,
        scene_count=3,
        asset_count=3,
    )

    assert report.passed is False
    assert any("1080x1920" in failure for failure in report.failures)


def test_validate_output_regression_rejects_missing_artifact(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="missing or empty"):
        validate_output(tmp_path / "missing.mp4", 30.0)
