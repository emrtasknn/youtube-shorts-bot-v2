import json
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from app.longform.render import description, render_film, still
from app.longform.spec import SpecError, load_film
from app.longform.timeline import LINE_GAP, SPEAKER_GAP, _chunks, build_timeline, to_srt
from app.studio.tts import SAMPLE_RATE, VoiceCast, VoiceRole


class _Tone:
    def __init__(self, name: str) -> None:
        self.name = name
        self.read: list[str] = []

    async def synth(self, text: str) -> Any:
        self.read.append(text)
        t = np.arange(int(0.25 * len(text.split()) * SAMPLE_RATE)) / SAMPLE_RATE
        return (0.4 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)


def _spec(tmp: Path, scenes: list[dict[str, Any]]) -> Path:
    img = np.full((300, 400, 3), 120, np.uint8)
    cv2.rectangle(img, (100, 80), (300, 220), (30, 60, 200), -1)
    (tmp / "img").mkdir(exist_ok=True)
    cv2.imwrite(str(tmp / "img" / "a.jpg"), img)
    p = tmp / "film.json"
    p.write_text(
        json.dumps({"title": "Test", "width": 320, "height": 180, "fps": 10, "scenes": scenes}),
        encoding="utf-8",
    )
    return p


def _cast() -> tuple[VoiceCast, _Tone, _Tone]:
    narrator, makam = _Tone("ema"), _Tone("piper")
    return VoiceCast(narrator, [VoiceRole("makam", makam, effect="phone")]), narrator, makam


SCENES: list[dict[str, Any]] = [
    {
        "kind": "document",
        "typed": ["İzinsiz uçuş.", "On gün ev hapsi."],
        "stamp": "Ceza",
        "say": [{"voice": "makam", "text": "İzinsiz uçuş. On gün ev hapsi."}],
    },
    {"kind": "chapter", "number": "1", "title": "Uçağını yakan adam", "hold": 1.5},
    {
        "kind": "photo",
        "image": "img/a.jpg",
        "label": "Test, 1925",
        "say": [
            {"text": "bin dokuz yüz yirmi beş", "sub": "1925"},
            {"text": "on beş dakika havada kalıyor"},
        ],
    },
    {"kind": "split", "image": "img/a.jpg", "image2": "img/a.jpg", "say": ["kimse ceza yazmadı"]},
    {"kind": "black", "hold": 1.0, "music": False},
]


@pytest.mark.asyncio
async def test_timeline_places_lines_and_routes_voices(tmp_path: Path) -> None:
    film = load_film(_spec(tmp_path, SCENES))
    cast, narrator, makam = _cast()
    tl = await build_timeline(film, cast)
    assert makam.read == ["İzinsiz uçuş. On gün ev hapsi."]
    assert narrator.read[0] == "bin dokuz yüz yirmi beş"
    assert tl.scenes[1].duration == pytest.approx(1.5)  # card without narration
    photo = [ln for ln in tl.lines if ln.scene == 2]
    assert photo[1].start - photo[0].end == pytest.approx(LINE_GAP, abs=0.01)
    assert photo[0].text == "1925"  # caption uses the written form
    assert all(a.end <= b.start for a, b in zip(tl.scenes, tl.scenes[1:], strict=False))
    assert len(tl.voice) == pytest.approx(tl.duration * SAMPLE_RATE, abs=2)
    assert SPEAKER_GAP > LINE_GAP


@pytest.mark.asyncio
async def test_tts_cache_avoids_second_synthesis(tmp_path: Path) -> None:
    film = load_film(_spec(tmp_path, SCENES))
    cast, narrator, _ = _cast()
    await build_timeline(film, cast, cache=tmp_path / "cache")
    first = len(narrator.read)
    await build_timeline(film, cast, cache=tmp_path / "cache")
    assert len(narrator.read) == first


def test_spec_errors_are_explicit(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="görsel bulunamadı"):
        load_film(_spec(tmp_path, [{"kind": "photo", "image": "img/yok.jpg", "say": ["x"]}]))
    with pytest.raises(SpecError, match="hold"):
        load_film(_spec(tmp_path, [{"kind": "chapter", "title": "x"}]))
    with pytest.raises(SpecError, match="hareket"):
        load_film(
            _spec(tmp_path, [{"kind": "photo", "image": "img/a.jpg", "move": "zip", "say": ["x"]}])
        )


def test_srt_splits_long_lines_and_keeps_order() -> None:
    long = "Bir. " + "kelime " * 40
    assert all(len(c) <= 84 for c in _chunks(long))
    assert " ".join(_chunks(long)).split() == long.split()


@pytest.mark.asyncio
async def test_still_and_full_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    film = load_film(_spec(tmp_path, SCENES))
    cast, _, _ = _cast()
    tl = await build_timeline(film, cast)
    png = still(film, tl, tl.scenes[2].start + 1.0, tmp_path / "s.png")
    frame = cv2.imread(str(png))
    assert frame.shape == (180, 320, 3) and frame.mean() > 20
    srt = to_srt(tl)
    assert "1925" in srt and "-->" in srt
    assert "0:00 Giriş" in description(film, tl, ["a.jpg (PD)"])

    monkeypatch.chdir(tmp_path)  # a relative output dir, as on GitHub Actions
    out = render_film(film, tl, Path("out"), workers=2, credits=["a"])
    assert out.video.is_file() and out.srt.is_file()
    dur = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(out.video),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert float(dur) == pytest.approx(tl.duration, abs=0.3)
