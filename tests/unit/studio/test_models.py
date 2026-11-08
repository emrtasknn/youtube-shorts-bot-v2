from pathlib import Path

from app.studio.models import Era, Line, Project, ProjectStatus, ProjectStore, Visual


def _project() -> Project:
    return Project(
        topic="Röntgen",
        lines=[
            Line("Bu ilk röntgen.", visual=1, kicker="1895"),
            Line("iks", card="X"),
            Line("Bugün", visual=2, era=Era.MODERN),
        ],
        visuals=[Visual("unused"), Visual("el röntgeni"), Visual("modern", source="file:/x.jpg")],
    )


def test_roundtrip() -> None:
    p = _project()
    q = Project.from_json(p.to_json())
    assert q == p


def test_missing_visuals_ignores_unused_and_cards() -> None:
    p = _project()
    assert p.missing_visuals() == [1]
    assert p.next_empty_visual() == 1
    assert p.validate() == []


def test_store_latest_for_chat(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    a = _project()
    a.chat_id, a.created_at = 5, 1.0
    b = _project()
    b.chat_id, b.created_at = 5, 2.0
    b.status = ProjectStatus.PUBLISHED
    store.save(a)
    store.save(b)
    latest = store.latest_for_chat(5)
    assert latest is not None and latest.id == a.id
