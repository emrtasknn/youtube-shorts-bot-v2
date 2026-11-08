"""SqlProjectStore against the migrated Postgres schema (CI runs alembic upgrade head)."""

from pathlib import Path
from uuid import uuid4

from app.infrastructure.database.connection import engine
from app.studio.models import Line, Project, ProjectStatus, UserPhoto, Visual
from app.studio.store_sql import SqlProjectStore


def test_studio_store_on_postgres(tmp_path: Path) -> None:
    store = SqlProjectStore(engine, tmp_path)
    chat = -(10**12) - (uuid4().int % 10**6)  # unique, below the 32-bit range like group ids
    open_p = Project(topic="Emu", lines=[Line("Emular kazandı.")], visuals=[Visual("emu")])
    open_p.chat_id, open_p.created_at = chat, 1.0
    done = Project(topic="Emu 2", lines=[Line("Bitti.")], visuals=[Visual("x")])
    done.chat_id, done.created_at, done.status = chat, 2.0, ProjectStatus.PUBLISHED
    store.save(open_p)
    store.save(done)
    open_p.title = "Güncel başlık"
    store.save(open_p)  # update path

    latest = store.latest_for_chat(chat)
    assert latest is not None and latest.id == open_p.id and latest.title == "Güncel başlık"
    assert store.load(done.id) == done

    assert store.add_to_inbox(chat, UserPhoto("telegram:1", "Emu askerleri")) == 1
    assert store.add_to_inbox(chat, UserPhoto("telegram:2")) == 2
    assert [p.source for p in store.inbox(chat)] == ["telegram:1", "telegram:2"]
    store.clear_inbox(chat)
    assert store.inbox(chat) == []
