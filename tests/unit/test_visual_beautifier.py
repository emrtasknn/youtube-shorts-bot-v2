from pathlib import Path

from PIL import Image

from app.application.services.visual_beautifier import VisualBeautifier


def test_beautifier_creates_portrait_image_with_deterministic_operations(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "beautified.jpg"

    Image.new("RGB", (1600, 900), "white").save(source)

    result = VisualBeautifier().beautify(source, output)

    assert result.changed is True
    assert result.output_path == output
    assert result.width == 1080
    assert result.height == 1920
    assert "portrait_center_crop" in result.operations
    assert "light_sharpen" in result.operations

    with Image.open(output) as image:
        assert image.size == (1080, 1920)
        assert image.format == "JPEG"


def test_beautifier_returns_original_when_processing_fails(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "beautified.jpg"

    Image.new("RGB", (800, 600), "white").save(source)

    beautifier = VisualBeautifier()
    beautifier._process = lambda *_args: (_ for _ in ()).throw(RuntimeError("boom"))

    result = beautifier.beautify(source, output)

    assert result.changed is False
    assert result.output_path == source
    assert result.width == 800
    assert result.height == 600
    assert result.operations == ()
    assert result.fallback_reason == "boom"
    assert not output.exists()
