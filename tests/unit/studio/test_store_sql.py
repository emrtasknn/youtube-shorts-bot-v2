from pathlib import Path

import sqlalchemy as sa

from app.studio.models import Line, Project, ProjectStatus, UserPhoto, Visual
from app.studio.store_sql import SqlProjectStore, metadata


def _store(tmp_path: Path) -> SqlProjectStore:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'studio.db'}")
    metadata.create_all(engine)
    return SqlProjectStore(engine, tmp_path / "work")


def _project(chat: int, created: float) -> Project:
    p = Project(topic="Emu Savaşı", lines=[Line("Emular kazandı.")], visuals=[Visual("emu")])
    p.chat_id, p.created_at = chat, created
    return p


def test_save_load_and_update(tmp_path: Path) -> None:
    store = _store(tmp_path)
    p = _project(-1001234567890, 1.0)  # Telegram group ids do not fit in 32 bits
    store.save(p)
    p.title = "Emular kazandı 🐦"
    p.visuals[0].source = "telegram:abc"
    store.save(p)
    q = store.load(p.id)
    assert q == p
    assert store.load("missing") is None


def test_latest_for_chat_skips_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    a, b, other = _project(5, 1.0), _project(5, 2.0), _project(6, 3.0)
    b.status = ProjectStatus.PUBLISHED
    for p in (a, b, other):
        store.save(p)
    latest = store.latest_for_chat(5)
    assert latest is not None and latest.id == a.id
    any_latest = store.latest_for_chat(5, active_only=False)
    assert any_latest is not None and any_latest.id == b.id
    assert store.latest_for_chat(7) is None


def test_inbox_survives_a_new_store_instance(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.add_to_inbox(9, UserPhoto("telegram:1", "Emu askerleri")) == 1
    assert store.add_to_inbox(9, UserPhoto("telegram:2")) == 2
    again = SqlProjectStore(store.engine, tmp_path / "work")  # e.g. after a restart
    assert [ph.source for ph in again.inbox(9)] == ["telegram:1", "telegram:2"]
    assert again.inbox(9)[0].note == "Emu askerleri"
    again.clear_inbox(9)
    assert store.inbox(9) == []
    assert store.workdir("abc").is_dir()
