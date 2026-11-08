import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.config.settings import Settings
from app.studio.webhook import StudioWebhook, public_url, webhook_secret


class _FakeBot:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    async def handle(self, update: dict[str, Any]) -> None:
        self.updates.append(update)


def _settings(tmp_path: Path, **kw: Any) -> Settings:
    return Settings(telegram_bot_token="123:abc", studio_dir=str(tmp_path), **kw)


async def _http(port: int, method: str, path: str, body: bytes = b"", headers: Any = None):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    head = f"{method} {path} HTTP/1.1\r\nHost: x\r\nContent-Length: {len(body)}\r\n"
    for k, v in (headers or {}).items():
        head += f"{k}: {v}\r\n"
    writer.write(head.encode() + b"\r\n" + body)
    await writer.drain()
    raw = await reader.read()
    writer.close()
    status = int(raw.split(b" ", 2)[1])
    return status, json.loads(raw.split(b"\r\n\r\n", 1)[1])


def test_secret_is_derived_and_stable(tmp_path: Path) -> None:
    s = _settings(tmp_path)
    assert webhook_secret(s) == webhook_secret(s)
    assert len(webhook_secret(s)) == 48 and webhook_secret(s).isalnum()
    assert webhook_secret(_settings(tmp_path, telegram_webhook_secret="given")) == "given"


def test_public_url_prefers_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://bot.onrender.com/")
    assert public_url(_settings(tmp_path)) == "https://bot.onrender.com"
    assert public_url(_settings(tmp_path, studio_public_url="https://x.io")) == "https://x.io"


@pytest.mark.asyncio
async def test_http_routes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    bot = _FakeBot()
    hook = StudioWebhook(bot, settings)  # type: ignore[arg-type]
    server = await asyncio.start_server(hook._client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    path = settings.telegram_webhook_path
    good = {"X-Telegram-Bot-Api-Secret-Token": hook.secret}
    update = json.dumps({"update_id": 41, "message": {"text": "/yeni Emu"}}).encode()
    async with server:
        assert (await _http(port, "GET", "/health"))[0] == 200
        assert (await _http(port, "GET", "/"))[0] == 200
        assert (await _http(port, "POST", "/other", update, good))[0] == 404
        assert (await _http(port, "POST", path, update))[0] == 401
        assert (
            await _http(
                port, "POST", path, update, {**good, "X-Telegram-Bot-Api-Secret-Token": "x"}
            )
        )[0] == 401
        assert (await _http(port, "POST", path, b"{not json", good))[0] == 400
        assert await _http(port, "POST", path, update, good) == (200, {"ok": True})
        assert (await _http(port, "POST", path, update, good))[0] == 200  # Telegram retry
        await asyncio.gather(*list(hook._tasks))
    assert bot.updates == [{"update_id": 41, "message": {"text": "/yeni Emu"}}]


@pytest.mark.asyncio
async def test_bot_errors_do_not_break_the_server(tmp_path: Path) -> None:
    class Boom(_FakeBot):
        async def handle(self, update: dict[str, Any]) -> None:
            raise RuntimeError("boom")

    hook = StudioWebhook(Boom(), _settings(tmp_path))  # type: ignore[arg-type]
    assert hook.accept({"update_id": 1})
    await asyncio.gather(*list(hook._tasks))
    assert not hook.accept({"update_id": 1})


def test_run_migrations_finds_repo_and_upgrades(monkeypatch: pytest.MonkeyPatch) -> None:
    from alembic import command

    from app.studio import webhook

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        command,
        "upgrade",
        lambda cfg, rev: calls.append((cfg.get_main_option("script_location"), rev)),
    )
    assert webhook.run_migrations() is True
    assert calls and calls[0][1] == "head" and calls[0][0].endswith("migrations")


@pytest.mark.asyncio
async def test_run_webhook_migrates_only_with_db_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.studio import webhook

    events: list[str] = []

    class StopServe(Exception):
        pass

    async def fake_set_webhook(self: Any, url: str, *, secret_token: str = "") -> dict[str, Any]:
        events.append(f"set:{url}")
        return {}

    async def fake_serve(self: Any, host: str, port: int) -> None:
        raise StopServe

    monkeypatch.setattr(webhook, "run_migrations", lambda: events.append("migrate") or True)
    monkeypatch.setattr("app.studio.telegram.StudioTelegram.set_webhook", fake_set_webhook)
    monkeypatch.setattr(webhook.StudioWebhook, "serve", fake_serve)

    with pytest.raises(StopServe):
        await webhook.run_webhook(_settings(tmp_path, studio_public_url="https://x.io"))
    assert events == ["set:https://x.io/telegram/webhook"]

    events.clear()
    url = f"sqlite:///{tmp_path / 'db.sqlite'}"
    with pytest.raises(StopServe):
        await webhook.run_webhook(
            _settings(
                tmp_path, studio_public_url="https://x.io", studio_store="db", database_url=url
            )
        )
    assert events == ["migrate", "set:https://x.io/telegram/webhook"]


def test_cli_keeps_bot_token_out_of_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    import logging

    from app.studio import cli

    monkeypatch.setattr(cli.asyncio, "run", lambda coro: coro.close())
    cli.main(["studio-script", "x"])
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
