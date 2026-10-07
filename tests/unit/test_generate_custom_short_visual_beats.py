from pathlib import Path
from types import SimpleNamespace

import pytest

from app.application.use_cases.generate_custom_short import GenerateCustomShort
from app.domain.enums import AssetStatus, AssetType
from app.infrastructure.database.models import SceneModel


class FakeDownloader:
    async def download(self, url: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"image")


class FakeRetriever:
    def __init__(self, stock_media: object) -> None:
        self.stock_media = stock_media

    async def retrieve(self, *, run_id: str, request_id: str, beat: object) -> object:
        return SimpleNamespace(
            beat=beat,
            provider="fake",
            query=f"query-{beat.beat_index}",
            item={
                "id": f"asset-{beat.beat_index}",
                "download_url": f"https://example.com/{beat.beat_index}.jpg",
                "source_url": f"https://example.com/source/{beat.beat_index}",
                "width": 1080,
                "height": 1920,
            },
            score=0.8 - (beat.beat_index * 0.1),
        )


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> GenerateCustomShort:
    import app.application.use_cases.generate_custom_short as module

    monkeypatch.setattr(module, "VisualBeatRetriever", FakeRetriever)
    return GenerateCustomShort(
        session=SimpleNamespace(),
        text=SimpleNamespace(),
        stock_media=SimpleNamespace(),
        tts=SimpleNamespace(),
        video_engine=SimpleNamespace(),
        downloader=FakeDownloader(),
        storage_root=tmp_path,
    )


def make_scene() -> SceneModel:
    return SceneModel(
        scene_index=2,
        duration=6,
        narration="The first sentence explains the event. The second sentence shows the consequence.",
        visual_goal="Show the event and its consequence",
        primary_subject="historical event",
        action="happens",
        era="20th century",
        location="Europe",
        must_show=["historical event"],
        must_avoid=["modern imagery"],
    )


@pytest.mark.asyncio
async def test_select_visual_beats_downloads_one_asset_per_beat(
    service: GenerateCustomShort,
) -> None:
    run = SimpleNamespace(id="run-1")
    scene = make_scene()

    selection = await service._select_visual_beats(run, scene)

    assert len(selection.timeline.beats) == 2
    assert len(selection.paths) == 2
    assert len(selection.assets) == 2
    assert selection.paths[0].name == "scene-2-beat-0.jpg"
    assert selection.paths[1].name == "scene-2-beat-1.jpg"
    assert all(path.exists() for path in selection.paths)
    assert all(asset.status == AssetStatus.READY for asset in selection.assets)
    assert all(asset.asset_type == AssetType.STOCK_IMAGE for asset in selection.assets)


@pytest.mark.asyncio
async def test_select_visual_beats_preserves_timed_render_contract(
    service: GenerateCustomShort,
) -> None:
    run = SimpleNamespace(id="run-1")
    scene = make_scene()

    selection = await service._select_visual_beats(run, scene)

    durations = tuple(beat.duration_seconds for beat in selection.timeline.beats)
    starts = tuple(beat.start_seconds for beat in selection.timeline.beats)
    assert starts[0] == 0.0
    assert starts[1] == pytest.approx(durations[0])
    assert sum(durations) == pytest.approx(6.0)

    metadata = [asset.asset_metadata["m18_visual_beat"] for asset in selection.assets]
    assert [item["beat_index"] for item in metadata] == [0, 1]
    assert [item["duration_seconds"] for item in metadata] == pytest.approx(durations)
    assert all(item["scene_index"] == 2 for item in metadata)
    assert all(item["beat_count"] == 2 for item in metadata)
