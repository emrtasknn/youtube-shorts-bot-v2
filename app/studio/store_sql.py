"""Postgres-backed Studio store (``STUDIO_STORE=db``).

Same interface as ``models.ProjectStore``, but projects and the photo pool live in
the database, so they survive restarts. This is what makes the bot work on a free
Render web service, whose disk is wiped every time it sleeps. Render inputs
(``workdir``) are still temporary local files.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.studio.models import Project, ProjectStatus, UserPhoto

metadata = sa.MetaData()

projects = sa.Table(
    "studio_projects",
    metadata,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("chat_id", sa.BigInteger, nullable=False, index=True),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("created_at", sa.Float, nullable=False),
    sa.Column("updated_at", sa.Float, nullable=False),
    sa.Column("data", sa.Text, nullable=False),
)

inbox = sa.Table(
    "studio_inbox",
    metadata,
    sa.Column("chat_id", sa.BigInteger, primary_key=True),
    sa.Column("data", sa.Text, nullable=False),
    sa.Column("updated_at", sa.Float, nullable=False),
)

_CLOSED = (ProjectStatus.PUBLISHED.value, ProjectStatus.CANCELLED.value)


class SqlProjectStore:
    def __init__(self, engine: Engine, workroot: Path) -> None:
        self.engine = engine
        self.root = workroot
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_url(cls, url: str, workroot: Path) -> SqlProjectStore:
        return cls(sa.create_engine(url, pool_pre_ping=True), workroot)

    # ---------- projects ----------
    def workdir(self, project_id: str) -> Path:
        d = self.root / project_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, project: Project) -> None:
        row = {
            "chat_id": project.chat_id,
            "status": project.status.value,
            "created_at": project.created_at,
            "updated_at": time.time(),
            "data": project.to_json(),
        }
        with self.engine.begin() as conn:
            updated = conn.execute(
                projects.update().where(projects.c.id == project.id).values(**row)
            ).rowcount
            if not updated:
                conn.execute(projects.insert().values(id=project.id, **row))

    def load(self, project_id: str) -> Project | None:
        with self.engine.connect() as conn:
            data = conn.execute(
                sa.select(projects.c.data).where(projects.c.id == project_id)
            ).scalar_one_or_none()
        return Project.from_json(data) if data else None

    def latest_with_video(self, chat_id: int, video_id: str = "") -> Project | None:
        """Newest project of this chat that has a YouTube video (or that exact video)."""
        q = (
            sa.select(projects.c.data)
            .where(projects.c.chat_id == chat_id)
            .order_by(projects.c.created_at.desc())
            .limit(50)
        )
        with self.engine.connect() as conn:
            rows: list[str] = list(conn.execute(q).scalars())
            for data in rows:
                p = Project.from_json(data)
                if p.youtube_id and (not video_id or p.youtube_id == video_id):
                    return p
        return None

    def latest_for_chat(self, chat_id: int, *, active_only: bool = True) -> Project | None:
        q = sa.select(projects.c.data).where(projects.c.chat_id == chat_id)
        if active_only:
            q = q.where(projects.c.status.not_in(_CLOSED))
        q = q.order_by(projects.c.created_at.desc()).limit(1)
        with self.engine.connect() as conn:
            data = conn.execute(q).scalar_one_or_none()
        return Project.from_json(data) if data else None

    # ---------- photo pool ----------
    def inbox(self, chat_id: int) -> list[UserPhoto]:
        with self.engine.connect() as conn:
            data = conn.execute(
                sa.select(inbox.c.data).where(inbox.c.chat_id == chat_id)
            ).scalar_one_or_none()
        if not data:
            return []
        try:
            raw = json.loads(data)
        except ValueError:
            return []
        return [
            UserPhoto(str(x.get("source", "")), str(x.get("note", "")))
            for x in raw
            if isinstance(x, dict) and x.get("source")
        ]

    def add_to_inbox(self, chat_id: int, photo: UserPhoto) -> int:
        photos = [*self.inbox(chat_id), photo]
        data = json.dumps([asdict(x) for x in photos], ensure_ascii=False)
        with self.engine.begin() as conn:
            updated = conn.execute(
                inbox.update()
                .where(inbox.c.chat_id == chat_id)
                .values(data=data, updated_at=time.time())
            ).rowcount
            if not updated:
                conn.execute(
                    inbox.insert().values(chat_id=chat_id, data=data, updated_at=time.time())
                )
        return len(photos)

    def clear_inbox(self, chat_id: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(inbox.delete().where(inbox.c.chat_id == chat_id))
