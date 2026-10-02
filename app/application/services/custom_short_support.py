from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def parse_script(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\\n", 1)[1].rsplit("```", 1)[0].strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Script response must be a JSON object")
    if not {"hook", "body", "duration_target", "scenes"}.issubset(data):
        raise ValueError("Script response is missing required fields")
    scenes = data["scenes"]
    if not isinstance(scenes, list) or not 3 <= len(scenes) <= 6:
        raise ValueError("Script must contain between 3 and 6 scenes")
    for scene in scenes:
        if not isinstance(scene, dict) or not scene.get("visual_query"):
            raise ValueError("Every scene needs a visual_query")
    return data

def validate_output(path: Path, duration_seconds: float) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("QC failed: rendered video is missing or empty")
    if not 15 <= duration_seconds <= 60:
        raise RuntimeError(f"QC failed: duration {duration_seconds:.2f}s is outside 15-60s")