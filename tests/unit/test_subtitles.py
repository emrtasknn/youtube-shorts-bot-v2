from __future__ import annotations

from pathlib import Path

import pytest

from app.application.services.subtitles import build_ass, write_ass


def test_build_ass_uses_safe_zone_and_timed_chunks() -> None:
    ass = build_ass("One two three four five six seven eight", 8.0)

    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    assert "Alignment, MarginL, MarginR, MarginV" in ass
    assert "390" in ass
    assert "0:00:00.00" in ass
    assert "0:00:08.00" in ass


def test_write_ass_creates_file(tmp_path: Path) -> None:
    path = write_ass(tmp_path / "captions.ass", "hello world", 2.0)
    assert path.is_file()
    assert "hello world" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_subtitles_are_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        build_ass(text, 2.0)
