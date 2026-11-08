from app.studio.models import Line, Project, Visual
from app.studio.render.planner import ImageInfo, plan_shots
from app.studio.text import distribute_words
from app.studio.tts import LineTiming


def test_plan_shots_cards_splits_and_modes() -> None:
    p = Project(
        topic="t",
        lines=[
            Line("Kısa giriş cümlesi burada.", visual=0),
            Line(
                "Bu satır çok uzun ve birkaç saniye boyunca devam eden bir anlatım içeriyor gerçekten.",
                visual=1,
            ),
            Line("iks", card="X"),
            Line("Son satır.", visual=1),
        ],
        visuals=[Visual("portrait"), Visual("landscape")],
    )
    timings = [
        LineTiming(0, 0.25, 2.5),
        LineTiming(1, 2.7, 12.0),
        LineTiming(2, 12.4, 12.8),
        LineTiming(3, 13.2, 15.0),
    ]
    words = []
    for lt in timings:
        words += distribute_words(p.lines[lt.index].shown, lt.start, lt.end, lt.index)
    images = {0: ImageInfo(800, 1000), 1: ImageInfo(1200, 800)}
    shots = plan_shots(p, timings, words, images, 15.2)
    assert shots[0].start == 0.0 and shots[0].mode == "bleed"  # portrait
    long_line = [s for s in shots if s.line == 1]
    assert len(long_line) >= 2  # 9 s line split into several cuts
    assert all(s.mode == "card" for s in long_line)  # landscape -> card layout
    title = [s for s in shots if s.mode == "title"]
    assert len(title) == 1 and title[0].card_text == "X"
    assert shots[-1].end == 15.2
    assert all(a.end == b.start for a, b in zip(shots, shots[1:], strict=False))
