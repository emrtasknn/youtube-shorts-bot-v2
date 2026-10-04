import pytest

from app.application.services.video_quality import (
    VideoQualityExpectation,
    VideoQualityGate,
)


def test_quality_gate_accepts_valid_vertical_output() -> None:
    report = VideoQualityGate().evaluate(
        duration_seconds=15.1,
        width=1080,
        height=1920,
        fps=30.0,
        has_audio=True,
        expected_duration=15.0,
        require_audio=True,
        subtitle_path_exists=True,
        subtitles_expected=True,
        scene_count=3,
        asset_count=3,
    )

    assert report.passed
    assert report.failures == ()


def test_quality_gate_rejects_wrong_dimensions_and_fps() -> None:
    report = VideoQualityGate().evaluate(
        duration_seconds=15.0,
        width=1920,
        height=1080,
        fps=29.0,
        has_audio=True,
    )

    assert not report.passed
    assert "output dimensions must be 1080x1920" in report.failures
    assert "output FPS must be 30" in report.failures


def test_quality_gate_requires_audio_when_requested() -> None:
    report = VideoQualityGate().evaluate(
        duration_seconds=10.0,
        width=1080,
        height=1920,
        fps=30.0,
        has_audio=False,
        require_audio=True,
    )

    assert report.failures == ("output audio stream is required",)


def test_quality_gate_rejects_duration_and_missing_subtitles() -> None:
    report = VideoQualityGate().evaluate(
        duration_seconds=10.5,
        width=1080,
        height=1920,
        fps=30.0,
        has_audio=True,
        expected_duration=10.0,
        subtitles_expected=True,
        subtitle_path_exists=False,
    )

    assert not report.passed
    assert len(report.failures) == 2


def test_quality_gate_rejects_mismatched_asset_count() -> None:
    report = VideoQualityGate().evaluate(
        duration_seconds=10.0,
        width=1080,
        height=1920,
        fps=30.0,
        has_audio=True,
        scene_count=3,
        asset_count=2,
    )

    assert report.failures == ("asset count must match scene count",)


def test_quality_expectation_rejects_invalid_tolerance() -> None:
    with pytest.raises(ValueError):
        VideoQualityExpectation(duration_tolerance_seconds=-1.0)
