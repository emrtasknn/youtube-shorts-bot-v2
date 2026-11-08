import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.studio.models import Era, Line, Project, Visual
from app.studio.render.pipeline import render_project
from app.studio.tts import SAMPLE_RATE

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


class ToneTTS:
    name = "tone"

    async def synth(self, text: str) -> np.ndarray:
        n = int(SAMPLE_RATE * (0.25 + 0.06 * len(text.split())))
        t = np.arange(n) / SAMPLE_RATE
        return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


@pytest.mark.asyncio
async def test_tiny_render_produces_video_and_thumbnails(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    paths = []
    for i, size in enumerate([(300, 400), (600, 400)]):
        arr = (rng.random((size[1], size[0], 3)) * 255).astype(np.uint8)
        path = tmp_path / f"{i}.jpg"
        Image.fromarray(arr).save(path)
        paths.append(path)
    project = Project(
        topic="test",
        title="Test",
        thumbnail_text="Garip tarih",
        lines=[
            Line("Bir iki üç dört.", visual=0, kicker="1895"),
            Line("iks", card="X"),
            Line("Beş altı yedi.", visual=1, era=Era.GOLD),
        ],
        visuals=[Visual("a", source=f"file:{paths[0]}"), Visual("b", source=f"file:{paths[1]}")],
    )
    out = await render_project(
        project, tmp_path / "work", ToneTTS(), width=216, height=384, fps=10, workers=1
    )
    assert out.video.is_file() and out.video.stat().st_size > 1000
    assert out.preview.is_file()
    assert out.thumb_vertical.is_file() and out.thumb_horizontal.is_file()
    assert 2.0 < out.duration < 6.0
