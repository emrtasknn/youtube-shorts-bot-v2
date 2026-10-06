from app.application.services.audio_quality import AudioQualityGate, parse_ffmpeg_audio_metrics


def test_audio_quality_gate_accepts_balanced_audio() -> None:
    report = AudioQualityGate().evaluate(
        max_volume_dbfs=-3.0,
        mean_volume_dbfs=-18.0,
        silence_ratio=0.08,
    )
    assert report.passed


def test_audio_quality_gate_rejects_clipping_and_excess_silence() -> None:
    report = AudioQualityGate().evaluate(
        max_volume_dbfs=0.2,
        mean_volume_dbfs=-18.0,
        silence_ratio=0.55,
    )
    assert not report.passed
    assert "audio peak is above -1 dBFS" in report.failures
    assert "audio silence ratio is too high" in report.failures


def test_audio_quality_metrics_parser() -> None:
    report = parse_ffmpeg_audio_metrics(
        """
        [Parsed_volumedetect] mean_volume: -17.2 dB
        [Parsed_volumedetect] max_volume: -2.4 dB
        [silencedetect] silence_duration: 0.5
        """,
        duration_seconds=10,
    )
    assert report.mean_volume_dbfs == -17.2
    assert report.max_volume_dbfs == -2.4
    assert report.silence_ratio == 0.05
