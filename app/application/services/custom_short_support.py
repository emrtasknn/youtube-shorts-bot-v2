from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.application.services.scene_contract import build_scene_contract

_GENERIC_VISUAL_TOKENS = {
    "crowd",
    "people",
    "person",
    "group",
    "city",
    "street",
    "historical",
    "history",
    "photo",
    "photograph",
    "image",
    "event",
    "scene",
}


def _coerce_seconds(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", "."))
        seconds = float(match.group()) if match else default
    else:
        seconds = default
    if not minimum <= seconds <= maximum:
        return default
    return seconds


def parse_script(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            raise ValueError("Invalid markdown-fenced JSON response")
        text = "\n".join(lines[1:-1]).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Script response must be a JSON object")
    if not {"hook", "body", "duration_target", "scenes"}.issubset(data):
        raise ValueError("Script response is missing required fields")
    data["hook"] = str(data["hook"]).strip()
    data["body"] = str(data["body"]).strip()
    data["cta"] = str(data.get("cta") or "").strip()
    if not data["hook"] or not data["body"]:
        raise ValueError("Script hook and body must not be empty")
    data["duration_target"] = _coerce_seconds(
        data["duration_target"], default=30.0, minimum=15.0, maximum=60.0
    )
    scenes = data["scenes"]
    if not isinstance(scenes, list) or not 3 <= len(scenes) <= 6:
        raise ValueError("Script must contain between 3 and 6 scenes")
    normalized_scenes: list[dict[str, Any]] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            raise ValueError("Scene must be an object")
        # LLMs occasionally return a single string for an optional string-list
        # field. Normalize that provider-specific shape before applying the
        # strict scene contract.
        scene = dict(scene)
        for field in ("entities", "must_show", "must_avoid"):
            value = scene.get(field)
            if isinstance(value, str):
                scene[field] = [value]
        contract = build_scene_contract(scene)
        query_tokens = {
            token.lower().strip(".,!?;:()[]{}")
            for token in contract.visual_query.split()
            if token.strip(".,!?;:()[]{}")
        }
        if query_tokens and query_tokens.issubset(_GENERIC_VISUAL_TOKENS):
            raise ValueError("Every scene needs a specific visual_query")
        normalized = contract.to_dict()
        normalized["duration"] = _coerce_seconds(
            scene.get("duration"), default=6.0, minimum=1.0, maximum=20.0
        )
        normalized_scenes.append(normalized)
    data["scenes"] = normalized_scenes
    return data


def validate_output(path: Path, duration_seconds: float) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("QC failed: rendered video is missing or empty")
    if not 15 <= duration_seconds <= 60:
        raise RuntimeError(f"QC failed: duration {duration_seconds:.2f}s is outside 15-60s")
