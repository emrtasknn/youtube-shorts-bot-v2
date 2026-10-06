import pytest

from app.application.services.audio_ducking import AudioDucking, DuckingConfig


def test_ducking_filter_uses_sidechain_compression() -> None:
    filter_graph = AudioDucking().build_filter()

    assert "[voice]asplit=2[voice_mix][voice_sidechain];" in filter_graph
    assert "[bgm][voice_sidechain]sidechaincompress=" in filter_graph
    assert "ratio=8" in filter_graph
    assert "attack=20" in filter_graph
    assert "release=250" in filter_graph
    assert "[voice_mix][ducked]amix=inputs=2" in filter_graph


def test_ducking_config_rejects_invalid_background_volume() -> None:
    with pytest.raises(ValueError, match="background_volume"):
        DuckingConfig(background_volume=1.1)


def test_ducking_config_accepts_custom_levels() -> None:
    filter_graph = AudioDucking(
        DuckingConfig(
            background_volume=0.12,
            threshold=0.05,
            ratio=6,
            attack_ms=15,
            release_ms=300,
        )
    ).build_filter()

    assert "volume=0.12" in filter_graph
    assert "threshold=0.05" in filter_graph
    assert "ratio=6" in filter_graph
    assert "attack=15" in filter_graph
    assert "release=300" in filter_graph
