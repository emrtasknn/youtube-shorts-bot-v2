"""Studio V3 data model.

A project is one Short: a script made of narration lines, a list of visuals the
lines point at, and the publishing metadata. Everything is plain JSON so the
Telegram bot, the CLI and the GitHub Actions renderer can hand a project to each
other without a database.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ProjectStatus(StrEnum):
    DRAFT = "draft"  # script written, waiting for script approval
    COLLECTING = "collecting"  # script approved, collecting visuals
    RENDERING = "rendering"
    REVIEW = "review"  # preview sent, waiting for publish approval
    SCHEDULED = "scheduled"  # private on YouTube, goes public at scheduled_at
    PUBLISHED = "published"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Era(StrEnum):
    OLD = "old"  # sepia archival grade
    MODERN = "modern"  # cool clean grade
    GOLD = "gold"  # warm highlight (awards, triumph)
    NEUTRAL = "neutral"


@dataclass(slots=True)
class Candidate:
    url: str
    thumb_url: str
    title: str
    license: str = ""
    attribution: str = ""


@dataclass(slots=True)
class Visual:
    """One picture the video needs. ``source`` is where the picture comes from:

    ``telegram:<file_id>``, ``url:<https url>`` or ``file:<local path>``.
    """

    description: str
    query: str = ""
    source: str = ""
    focus_x: float | None = None
    focus_y: float | None = None
    attribution: str = ""
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def filled(self) -> bool:
        return bool(self.source)


@dataclass(slots=True)
class UserPhoto:
    """A picture the user sent before (or together with) the topic.

    ``source`` uses the same scheme as ``Visual.source``; ``note`` is the photo's
    caption ("Emu askerleri 1932") and tells the script writer what it shows.
    """

    source: str
    note: str = ""


@dataclass(slots=True)
class Line:
    """One narration line == one shot (long lines are split by the planner).

    ``narration`` is what the TTS reads: numbers spelled out, foreign names
    written phonetically. ``caption`` is what is shown on screen.
    ``visual`` indexes ``Project.visuals``; ``card`` replaces the picture with a
    big animated title card (the "X" moment).
    """

    narration: str
    caption: str = ""
    visual: int = 0
    kicker: str = ""
    era: Era = Era.OLD
    card: str = ""

    @property
    def shown(self) -> str:
        return self.caption or self.narration


@dataclass(slots=True)
class Project:
    topic: str
    lines: list[Line] = field(default_factory=list)
    visuals: list[Visual] = field(default_factory=list)
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    pinned_comment: str = ""
    thumbnail_text: str = ""
    thumbnail_visual: int = 0
    status: ProjectStatus = ProjectStatus.DRAFT
    chat_id: int = 0
    youtube_id: str = ""
    scheduled_at: str = ""  # RFC 3339 UTC, when YouTube makes it public
    error: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    created_at: float = field(default_factory=time.time)

    # ---------- helpers ----------
    def missing_visuals(self) -> list[int]:
        used = {ln.visual for ln in self.lines if not ln.card}
        return [
            i for i in sorted(used) if 0 <= i < len(self.visuals) and not self.visuals[i].filled
        ]

    def next_empty_visual(self) -> int | None:
        missing = self.missing_visuals()
        if missing:
            return missing[0]
        for i, v in enumerate(self.visuals):
            if not v.filled:
                return i
        return None

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.lines:
            problems.append("Metin boş.")
        for i, ln in enumerate(self.lines, 1):
            if not ln.narration.strip():
                problems.append(f"{i}. satırın anlatımı boş.")
            if not ln.card and not 0 <= ln.visual < len(self.visuals):
                problems.append(f"{i}. satır olmayan bir görsele bağlı ({ln.visual + 1}).")
        return problems

    # ---------- serialization ----------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=1)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        visuals = [
            Visual(
                description=str(v.get("description", "")),
                query=str(v.get("query", "")),
                source=str(v.get("source", "")),
                focus_x=v.get("focus_x"),
                focus_y=v.get("focus_y"),
                attribution=str(v.get("attribution", "")),
                candidates=[Candidate(**c) for c in v.get("candidates", [])],
            )
            for v in data.get("visuals", [])
        ]
        lines = [
            Line(
                narration=str(ln.get("narration", "")),
                caption=str(ln.get("caption", "")),
                visual=int(ln.get("visual", 0)),
                kicker=str(ln.get("kicker", "")),
                era=_era(ln.get("era")),
                card=str(ln.get("card", "")),
            )
            for ln in data.get("lines", [])
        ]
        return cls(
            topic=str(data.get("topic", "")),
            lines=lines,
            visuals=visuals,
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            tags=[str(t) for t in data.get("tags", [])],
            pinned_comment=str(data.get("pinned_comment", "")),
            thumbnail_text=str(data.get("thumbnail_text", "")),
            thumbnail_visual=int(data.get("thumbnail_visual", 0)),
            status=ProjectStatus(data.get("status", ProjectStatus.DRAFT)),
            chat_id=int(data.get("chat_id", 0)),
            youtube_id=str(data.get("youtube_id", "")),
            scheduled_at=str(data.get("scheduled_at", "")),
            error=str(data.get("error", "")),
            id=str(data.get("id") or uuid.uuid4().hex[:10]),
            created_at=float(data.get("created_at", time.time())),
        )

    @classmethod
    def from_json(cls, text: str) -> Project:
        return cls.from_dict(json.loads(text))


def _era(value: object) -> Era:
    try:
        return Era(str(value or Era.OLD))
    except ValueError:
        return Era.OLD


class ProjectStore:
    """One JSON file per project. Small, inspectable, no migrations."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, project_id: str) -> Path:
        return self.root / project_id / "project.json"

    def workdir(self, project_id: str) -> Path:
        d = self.root / project_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, project: Project) -> None:
        p = self.path(project.id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(project.to_json(), encoding="utf-8")
        tmp.replace(p)

    def load(self, project_id: str) -> Project | None:
        p = self.path(project_id)
        if not p.is_file():
            return None
        return Project.from_json(p.read_text(encoding="utf-8"))

    # ---------- per-chat photo pool (pictures waiting for the next /yeni) ----------
    def _inbox_path(self, chat_id: int) -> Path:
        return self.root / "_inbox" / f"{chat_id}.json"

    def inbox(self, chat_id: int) -> list[UserPhoto]:
        p = self._inbox_path(chat_id)
        if not p.is_file():
            return []
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return []
        return [
            UserPhoto(str(x.get("source", "")), str(x.get("note", "")))
            for x in raw
            if isinstance(x, dict) and x.get("source")
        ]

    def add_to_inbox(self, chat_id: int, photo: UserPhoto) -> int:
        photos = self.inbox(chat_id)
        photos.append(photo)
        p = self._inbox_path(chat_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([asdict(x) for x in photos], ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(p)
        return len(photos)

    def clear_inbox(self, chat_id: int) -> None:
        self._inbox_path(chat_id).unlink(missing_ok=True)

    def latest_with_video(self, chat_id: int, video_id: str = "") -> Project | None:
        """Newest project of this chat that has a YouTube video (or that exact video)."""
        best: Project | None = None
        for p in self.root.glob("*/project.json"):
            try:
                proj = Project.from_json(p.read_text(encoding="utf-8"))
            except (ValueError, KeyError):
                continue
            if proj.chat_id != chat_id or not proj.youtube_id:
                continue
            if video_id and proj.youtube_id != video_id:
                continue
            if best is None or proj.created_at > best.created_at:
                best = proj
        return best

    def latest_for_chat(self, chat_id: int, *, active_only: bool = True) -> Project | None:
        best: Project | None = None
        for p in self.root.glob("*/project.json"):
            try:
                proj = Project.from_json(p.read_text(encoding="utf-8"))
            except (ValueError, KeyError):
                continue
            if proj.chat_id != chat_id:
                continue
            if active_only and proj.status in (
                ProjectStatus.PUBLISHED,
                ProjectStatus.CANCELLED,
            ):
                continue
            if best is None or proj.created_at > best.created_at:
                best = proj
        return best
