import json
from pathlib import Path

import pytest

from app.application.services.custom_short_support import parse_script, validate_output

def test_parse_script_accepts_valid_json() -> None:
    payload = {"hook": "H", "body": "B", "duration_target": 28, "scenes": [{"visual_query": "roman"}] * 3}
    result = parse_script(json.dumps(payload))
    assert result["hook"] == "H"
    assert len(result["scenes"]) == 3

def test_parse_script_rejects_missing_scene_query() -> None:
    payload = {"hook": "H", "body": "B", "duration_target": 28, "scenes": [{"visual_query": ""}] * 3}
    with pytest.raises(ValueError, match="visual_query"):
        parse_script(json.dumps(payload))

def test_validate_output_rejects_empty_file(tmp_path: Path) -> None:
    output = tmp_path / "video.mp4"
    output.touch()
    with pytest.raises(RuntimeError, match="missing or empty"):
        validate_output(output, 30)