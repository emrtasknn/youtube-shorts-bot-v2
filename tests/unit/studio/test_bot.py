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
