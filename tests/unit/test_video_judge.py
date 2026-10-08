from pathlib import Path

from app.application.services.video_judge import AutomatedVideoJudge, VideoJudgeInput


def _input(tmp_path: Path, **overrides: object) -> VideoJudgeInput:
    output = tmp_path / "short.mp4"
    output.write_bytes(b"mp4")
    values = {
        "output_path": output,
        "duration_seconds": 30.0,
        "width": 1080,
        "height": 1920,
        "fps": 30.0,
        "has_audio": True,
        "expected_duration_seconds": 30.0,
        "scene_count": 5,
        "asset_count": 5,
        "narration_word_count": 90,
        "subtitle_text": "A complete short-form narration.",
        "synchronization": {"issues": []},
        "audio_qc_passed": True,
        "audio_qc_failures": (),
        "fallback_asset_count": 0,
    }
    values.update(overrides)
    return VideoJudgeInput(**values)


def test_judge_passes_clean_render(tmp_path: Path) -> None:
    report = AutomatedVideoJudge().evaluate(_input(tmp_path))

    assert report.decision == "PASS"
    assert report.passed
    assert report.score == 100.0
    assert report.failures == ()


def test_judge_warns_on_non_blocking_sync_issue(tmp_path: Path) -> None:
    report = AutomatedVideoJudge().evaluate(
        _input(tmp_path, synchronization={"issues": [{"severity": "warning"}]})
    )

    assert report.decision == "PASS_WITH_WARNINGS"
    assert "synchronization contains non-blocking issues" in report.warnings


def test_judge_retries_when_visual_fallbacks_are_excessive(tmp_path: Path) -> None:
    report = AutomatedVideoJudge().evaluate(
        _input(tmp_path, fallback_asset_count=3)
    )

    assert report.decision == "RETRY"
    assert report.retry_reasons == ("excessive_visual_fallbacks",)


def test_judge_rejects_blocking_technical_failure(tmp_path: Path) -> None:
    report = AutomatedVideoJudge().evaluate(
        _input(tmp_path, width=720, has_audio=False)
    )

    assert report.decision == "REJECT"
    assert "output dimensions are not 1080x1920" in report.failures
    assert "output audio stream is missing" in report.failures


def test_judge_retries_audio_qc_failure(tmp_path: Path) -> None:
    report = AutomatedVideoJudge().evaluate(
        _input(tmp_path, audio_qc_passed=False, audio_qc_failures=("clipping",))
    )

    assert report.decision == "RETRY"
    assert report.retry_reasons == ("audio_qc_failed",)


def test_judge_rejects_blocking_synchronization_failure(tmp_path: Path) -> None:
    report = AutomatedVideoJudge().evaluate(
        _input(
            tmp_path,
            synchronization={"issues": [{"severity": "error", "code": "major_scene_duration_drift"}]},
        )
    )

    assert report.decision == "REJECT"
    assert "synchronization contains blocking errors" in report.failures
