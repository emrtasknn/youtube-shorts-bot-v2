from __future__ import annotations

import re
from pathlib import Path

from app.application.services.subtitle_engine import SubtitleEngine


def _format_ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _wrap_text(text: str, max_words: int = 3) -> list[str]:
    words = re.findall(r"\S+", text.strip())
    return [" ".join(words[index : index + max_words]) for index in range(0, len(words), max_words)]


def build_ass(text: str, duration_seconds: float) -> str:
    cues = SubtitleEngine().build_cues(text, duration_seconds)
    events: list[str] = []
    for cue in cues:
        wrapped = "\\N".join(_wrap_text(cue.text))
        events.append(
            f"Dialogue: 0,{_format_ass_time(cue.start_seconds)},"
            f"{_format_ass_time(cue.end_seconds)},Default,,0,0,0,,{wrapped}"
        )

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,62,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,1,0,0,0,100,100,0,0,1,4,1,2,80,80,390,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header + "\n".join(events) + "\n"


def write_ass(path: Path, text: str, duration_seconds: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_ass(text, duration_seconds), encoding="utf-8")
    return path
