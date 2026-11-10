import pytest

from app.studio import analytics
from app.studio.models import Line, Project, Visual


def _curve(duration: float, fn) -> list[tuple[float, float]]:
    return [(i / 100, fn(i / 100 * duration)) for i in range(1, 101)]


def test_parse_video_id_and_duration() -> None:
    vid = "Ab3_dE-fGh1"
    for text in (
        vid,
        f"https://youtube.com/shorts/{vid}",
        f"https://www.youtube.com/watch?v={vid}&t=3",
        f"https://youtu.be/{vid}",
    ):
        assert analytics.parse_video_id(text) == vid
    assert analytics.parse_video_id("merhaba") is None
    assert analytics.parse_duration("PT55S") == 55
    assert analytics.parse_duration("PT1M2S") == 62
    assert analytics.parse_duration("") == 0


def test_analyze_finds_hook_leak_cliffs_and_rewatch() -> None:
    def watch(t: float) -> float:
        if t < 1:
            return 1.0
        if t < 3:
            return 1.0 - 0.15 * (t - 1)  # 1.0 -> 0.7 by the 3rd second
        if t < 20:
            return 0.7
        if t < 22:
            return 0.7 - 0.1 * (t - 20)  # cliff: -0.2 at 20-22 s
        return 0.5

    ret = analytics.analyze(_curve(55, watch), 55)
    assert ret.hook_kept == pytest.approx(0.7, abs=0.05)  # points are ~0.5 s apart
    assert ret.cliffs and 19 <= ret.cliffs[0].start <= 21
    assert ret.cliffs[0].drop == pytest.approx(0.2, abs=0.03)
    assert ret.end_kept == pytest.approx(0.5, abs=0.03)
    assert not ret.rewatch

    looping = analytics.analyze(_curve(30, lambda t: 1.0 if t < 25 else 1.2), 30)
    assert looping.rewatch and not looping.cliffs


def test_report_names_the_line_and_gives_advice() -> None:
    project = Project(
        topic="t",
        lines=[Line("Bir iki üç dört beş altı yedi sekiz.") for _ in range(10)],
        visuals=[Visual("v")],
    )
    ret = analytics.analyze(_curve(50, lambda t: 1.0 if t < 1 else (0.55 if t < 26 else 0.3)), 50)
    analytics.attach_lines(ret, project)
    assert ret.cliffs[-1].line == 4  # ~25 s is the 5th of ten equal lines
    text = analytics.report(
        "Video", {"views": 12345, "averageViewPercentage": 64, "likes": 9}, ret, project
    )
    assert "12.345 izlenme" in text and "%64" in text
    assert "Açılış zayıf" in text
    assert "5. satır" in text
    assert analytics.report("V", {}, ret, None).count("satır eşleştirmesi yapılamadı") == 1


def test_empty_curve_is_an_error() -> None:
    with pytest.raises(ValueError):
        analytics.analyze([], 30)
