import json
from pathlib import Path

import pytest

from app.application.services.custom_short_support import parse_script, validate_output


def test_parse_script_accepts_valid_json() -> None:
    payload = {
        "hook": "H",
        "body": "B",
        "duration_target": 28,
        "scenes": [
            {"visual_query": "Rome Colosseum", "visual_goal": "Roman Colosseum", "narration": "Romans gathered."}
        ] * 3,
    }
    result = parse_script(json.dumps(payload))
    assert result["hook"] == "H"
    assert len(result["scenes"]) == 3


def test_parse_script_normalizes_human_readable_durations() -> None:
    payload = {
        "hook": "H",
        "body": "B",
        "duration_target": "about 30 seconds",
        "scenes": [
            {
                "visual_query": "Roman Colosseum",
                "visual_goal": "Roman Colosseum",
                "narration": "Romans gathered.",
                "duration": "6 seconds",
            }
        ] * 3,
    }
    result = parse_script(json.dumps(payload))
    assert result["duration_target"] == 30.0
    assert result["scenes"][0]["duration"] == 6.0


def test_parse_script_uses_safe_defaults_for_invalid_durations() -> None:
    payload = {
        "hook": "H",
        "body": "B",
        "duration_target": "thirty seconds",
        "scenes": [
            {
                "visual_query": "Roman Colosseum",
                "visual_goal": "Roman Colosseum",
                "narration": "Romans gathered.",
                "duration": "unknown",
            }
        ] * 3,
    }
    result = parse_script(json.dumps(payload))
    assert result["duration_target"] == 30.0
    assert result["scenes"][0]["duration"] == 6.0


def test_parse_script_rejects_missing_scene_query() -> None:
    payload = {
        "hook": "H",
        "body": "B",
        "duration_target": 28,
        "scenes": [
            {"visual_query": "", "visual_goal": "Roman Colosseum", "narration": "Romans gathered."}
        ] * 3,
    }
    with pytest.raises(ValueError, match="visual_query"):
        parse_script(json.dumps(payload))


def test_validate_output_rejects_empty_file(tmp_path: Path) -> None:
    output = tmp_path / "video.mp4"
    output.touch()
    with pytest.raises(RuntimeError, match="missing or empty"):
        validate_output(output, 30.0)

def test_parse_script_rejects_missing_scene_narration() -> None:
    payload = {
        "hook": "H",
        "body": "B",
        "duration_target": 28,
        "scenes": [
            {"visual_query": "Roman Colosseum", "visual_goal": "Roman Colosseum", "narration": ""}
        ]
        * 3,
    }
    with pytest.raises(ValueError, match="narration"):
        parse_script(json.dumps(payload))


def test_parse_script_rejects_generic_visual_query() -> None:
    payload = {
        "hook": "H",
        "body": "B",
        "duration_target": 28,
        "scenes": [
            {
                "visual_query": "crowd people historical photo",
                "visual_goal": "Specific historical event",
                "narration": "A specific event happened.",
            }
        ]
        * 3,
    }
    with pytest.raises(ValueError, match="specific visual_query"):
        parse_script(json.dumps(payload))
