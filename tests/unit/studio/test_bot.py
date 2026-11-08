import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.config.settings import Settings
from app.studio import bot as bot_module
from app.studio.bot import StudioBot
from app.studio.models import ProjectStatus
from app.studio.script_writer import ScriptWriter

from .test_script_writer import LLM_OUTPUT, FakeLLM


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, Any]] = []

    async def send_long(self, chat_id: int, text: str, reply_markup: Any = None) -> None:
        self.sent.append((chat_id, text, reply_markup))

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        return None

    async def answer_callback(self, callback_query_id: str, text: str) -> None:
        return None

    @property
    def last(self) -> str:
        return self.sent[-1][1]

    def last_buttons(self) -> list[str]:
        markup = self.sent[-1][2] or {"inline_keyboard": []}
        return [b["callback_data"] for row in markup["inline_keyboard"] for b in row]


def _bot(tmp_path: Path, **overrides: Any) -> tuple[StudioBot, FakeTelegram]:
    settings = Settings(
        telegram_bot_token="123:abc",
        telegram_admin_user_id=7,
        studio_dir=str(tmp_path),
        **overrides,
    )
    b = StudioBot(settings)
    fake = FakeTelegram()
    b.bot = fake  # type: ignore[assignment]
    b._writer = ScriptWriter(FakeLLM(LLM_OUTPUT))
    return b, fake


def _msg(text: str = "", **extra: Any) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {"chat": {"id": 99}, "from": {"id": 7}, "text": text, **extra},
    }


def _cb(data: str) -> dict[str, Any]:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "q",
            "from": {"id": 7},
            "message": {"chat": {"id": 99}},
            "data": data,
        },
    }


@pytest.mark.asyncio
async def test_full_flow_until_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    b, tg = _bot(tmp_path, studio_render_mode="github")
    await b.handle(_msg("/yeni Röntgen'in keşfi"))
    assert "METİN" in tg.last
    p = b.current(99)
    assert p is not None and p.status == ProjectStatus.DRAFT

    await b.handle(_msg("2: 8 Kasım 1895 akşamı"))
    p = b.current(99)
    assert p is not None
    assert p.lines[1].caption == "8 Kasım 1895 akşamı"
    assert "bin sekiz yüz doksan beş" in p.lines[1].narration

    await b.handle(_cb(f"ok:{p.id}"))
    assert b.current(99).status == ProjectStatus.COLLECTING  # type: ignore[union-attr]
    assert f"find:{p.id}" in tg.last_buttons()

    # photo without caption fills the first missing visual, caption "2" targets g2
    await b.handle(
        _msg(photo=[{"file_id": "small", "file_size": 1}, {"file_id": "big", "file_size": 9}])
    )
    await b.handle(_msg(photo=[{"file_id": "p1", "file_size": 5}], caption="2"))
    p = b.current(99)
    assert p is not None
    assert p.visuals[0].source == "telegram:big"
    assert p.visuals[1].source == "telegram:p1"
    assert p.missing_visuals() == []

    dispatched: list[str] = []

    async def fake_dispatch(project: Any, settings: Any) -> None:
        dispatched.append(project.id)

    monkeypatch.setattr(bot_module, "dispatch_github", fake_dispatch)
    await b.handle(_cb(f"render:{p.id}"))
    assert dispatched == [p.id]
    assert "GitHub Actions" in tg.last


@pytest.mark.asyncio
async def test_render_refused_when_visuals_missing(tmp_path: Path) -> None:
    b, tg = _bot(tmp_path)
    await b.handle(_msg("/yeni Emu Savaşı"))
    await b.handle(_msg("/render"))
    assert "Eksik görseller" in tg.last


@pytest.mark.asyncio
async def test_ignores_strangers(tmp_path: Path) -> None:
    b, tg = _bot(tmp_path)
    upd = _msg("/yeni x")
    upd["message"]["from"]["id"] = 1
    await b.handle(upd)
    assert tg.sent == []


@pytest.mark.asyncio
async def test_line_visual_reassign_and_visual_edit(tmp_path: Path) -> None:
    b, tg = _bot(tmp_path)
    await b.handle(_msg("/yeni Röntgen"))
    await b.handle(_msg("1 -> 1"))
    await b.handle(_msg("g2: Anna Bertha'nın el röntgeni"))
    p = b.current(99)
    assert p is not None
    assert p.lines[0].visual == 0
    assert p.visuals[1].description == "Anna Bertha'nın el röntgeni"


def _photo(file_id: str, caption: str = "", album: str = "") -> dict[str, Any]:
    extra: dict[str, Any] = {"photo": [{"file_id": file_id, "file_size": 1}]}
    if caption:
        extra["caption"] = caption
    if album:
        extra["media_group_id"] = album
    return _msg(**extra)


@pytest.mark.asyncio
async def test_photos_before_topic_go_to_pool_and_fill_visuals(tmp_path: Path) -> None:
    b, tg = _bot(tmp_path)
    await b.handle(_photo("f1", "Röntgen laboratuvarı"))
    assert "Havuza eklendi (1)" in tg.last
    await b.handle(_photo("f2"))
    await b.handle(_msg("/havuz"))
    assert "Havuzda 2 fotoğraf" in tg.last and "Röntgen laboratuvarı" in tg.last

    await b.handle(_msg("/yeni Röntgen'in keşfi"))
    assert any("2 fotoğrafın kullanılacak" in m[1] for m in tg.sent)
    p = b.current(99)
    assert p is not None
    assert [v.source for v in p.visuals[:2]] == ["telegram:f1", "telegram:f2"]
    assert b.store.inbox(99) == []  # pool is emptied once used
    assert "KULLANICININ FOTOĞRAFLARI (2 adet" in b.writer._llm.calls[-1]  # type: ignore[attr-defined]

    # rewriting from scratch keeps the user's photos
    await b.handle(_cb(f"rw:{p.id}"))
    p = b.current(99)
    assert p is not None
    assert [v.source for v in p.visuals[:2]] == ["telegram:f1", "telegram:f2"]


@pytest.mark.asyncio
async def test_album_with_yeni_caption_starts_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bot_module, "ALBUM_WAIT", 0)
    b, tg = _bot(tmp_path)
    await b.handle(_photo("a1", "/yeni Röntgen'in keşfi", album="G"))
    await b.handle(_photo("a2", album="G"))
    await b.handle(_photo("a3", album="G"))
    await asyncio.gather(*list(b._jobs))
    p = b.current(99)
    assert p is not None and p.topic == "Röntgen'in keşfi"
    assert [v.source for v in p.visuals[:3]] == ["telegram:a1", "telegram:a2", "telegram:a3"]
    assert not any("Havuza eklendi" in m[1] for m in tg.sent)


@pytest.mark.asyncio
async def test_plus_caption_pools_photo_while_project_open(tmp_path: Path) -> None:
    b, tg = _bot(tmp_path)
    await b.handle(_msg("/yeni Röntgen'in keşfi"))
    await b.handle(_photo("x", "+ sonraki video için"))
    assert "Havuza eklendi (1)" in tg.last
    p = b.current(99)
    assert p is not None and not any(v.filled for v in p.visuals)
    assert b.store.inbox(99)[0].note == "sonraki video için"
    await b.handle(_msg("/havuz temizle"))
    assert b.store.inbox(99) == []


@pytest.mark.asyncio
async def test_bot_with_database_store_keeps_state_across_restarts(tmp_path: Path) -> None:
    import sqlalchemy as sa

    from app.studio.store_sql import SqlProjectStore, metadata

    url = f"sqlite:///{tmp_path / 'studio.db'}"
    metadata.create_all(sa.create_engine(url))
    b, _ = _bot(tmp_path, studio_store="db", database_url=url)
    assert isinstance(b.store, SqlProjectStore)
    await b.handle(_photo("f1", "Emu askerleri"))
    await b.handle(_msg("/yeni Röntgen'in keşfi"))
    p = b.current(99)
    assert p is not None and p.visuals[0].source == "telegram:f1"

    restarted, tg = _bot(tmp_path, studio_store="db", database_url=url)  # free host woke up
    await restarted.handle(_cb(f"ok:{p.id}"))
    q = restarted.current(99)
    assert q is not None and q.id == p.id and q.status == ProjectStatus.COLLECTING
    assert "Proje bulunamadı" not in tg.last
