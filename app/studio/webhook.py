"""Studio bot over a Telegram webhook (``python -m app studio-webhook``).

Polling needs a process that never sleeps (a paid worker). A webhook lets the bot
run on a free Render web service: Telegram POSTs each update, which also wakes the
service. Everything runs in one asyncio loop, so the bot's background tasks
(album wait, local renders) keep working between requests.

Minimal HTTP on ``asyncio.start_server``: no extra dependency.
  GET  /  or /health          -> 200 (Render health check)
  POST <TELEGRAM_WEBHOOK_PATH> -> 200 at once, the update is handled in the background
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from collections import deque
from pathlib import Path
from typing import Any

from app.config.settings import Settings
from app.studio.bot import StudioBot

log = logging.getLogger("studio.webhook")

MAX_BODY = 1_000_000


def webhook_secret(settings: Settings) -> str:
    """TELEGRAM_WEBHOOK_SECRET, or one derived from the bot token (Telegram: [A-Za-z0-9_-])."""
    if settings.telegram_webhook_secret:
        return settings.telegram_webhook_secret
    return hashlib.sha256(f"studio:{settings.telegram_bot_token}".encode()).hexdigest()[:48]


def run_migrations() -> bool:
    """``alembic upgrade head`` from inside the app.

    Render runs the Docker Command without a shell, so ``a && b`` cannot be used
    there; the bot migrates its own database at start instead.
    """
    for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
        ini = base / "alembic.ini"
        if ini.is_file() and (base / "migrations").is_dir():
            from alembic import command
            from alembic.config import Config

            cfg = Config(str(ini))
            cfg.set_main_option("script_location", str(base / "migrations"))
            command.upgrade(cfg, "head")
            return True
    log.warning("alembic.ini bulunamadı; migration atlandı")
    return False


def public_url(settings: Settings) -> str:
    return (settings.studio_public_url or os.environ.get("RENDER_EXTERNAL_URL", "")).rstrip("/")


class StudioWebhook:
    def __init__(self, bot: StudioBot, settings: Settings) -> None:
        self.bot = bot
        self.path = settings.telegram_webhook_path
        self.secret = webhook_secret(settings)
        self._seen: deque[int] = deque(maxlen=500)  # Telegram retries slow answers
        self._tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------ dispatch
    def accept(self, update: dict[str, Any]) -> bool:
        """Queue one update; False when it is a repeat."""
        uid = update.get("update_id")
        if isinstance(uid, int):
            if uid in self._seen:
                return False
            self._seen.append(uid)
        task = asyncio.create_task(self._handle(update))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def _handle(self, update: dict[str, Any]) -> None:
        try:
            await self.bot.handle(update)
        except Exception:
            log.exception("update failed")

    # ------------------------------------------------------------ HTTP
    async def respond(
        self, method: str, path: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, dict[str, Any]]:
        path = path.split("?", 1)[0]
        if method in ("GET", "HEAD") and path in ("/", "/health"):
            return 200, {"ok": True, "service": "studio-bot"}
        if method != "POST" or path != self.path:
            return 404, {"error": "not_found"}
        supplied = headers.get("x-telegram-bot-api-secret-token", "")
        if not hmac.compare_digest(supplied, self.secret):
            return 401, {"error": "unauthorized"}
        try:
            update = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return 400, {"ok": False}
        if not isinstance(update, dict):
            return 400, {"ok": False}
        self.accept(update)
        return 200, {"ok": True}

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        status: int = 400
        payload: dict[str, Any] = {"ok": False}
        try:
            request = (await asyncio.wait_for(reader.readline(), 30)).decode("latin-1")
            parts = request.split()
            if len(parts) >= 2:
                headers: dict[str, str] = {}
                while True:
                    line = (await asyncio.wait_for(reader.readline(), 30)).decode("latin-1")
                    if line in ("\r\n", "\n", ""):
                        break
                    name, _, value = line.partition(":")
                    headers[name.strip().lower()] = value.strip()
                length = int(headers.get("content-length", "0") or 0)
                if length > MAX_BODY:
                    status, payload = 413, {"error": "too_large"}
                else:
                    body = await asyncio.wait_for(reader.readexactly(length), 30) if length else b""
                    status, payload = await self.respond(parts[0], parts[1], headers, body)
        except (TimeoutError, ValueError, asyncio.IncompleteReadError, ConnectionError):
            pass
        data = json.dumps(payload).encode()
        reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found"}
        head = (
            f"HTTP/1.1 {status} {reason.get(status, 'Error')}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n"
        )
        try:
            writer.write(head.encode() + data)
            await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()

    async def serve(self, host: str, port: int) -> None:
        server = await asyncio.start_server(self._client, host, port)
        log.info("Studio webhook listening on %s:%s%s", host, port, self.path)
        async with server:
            await server.serve_forever()


async def run_webhook(settings: Settings) -> None:
    base = public_url(settings)
    if not base:
        raise RuntimeError(
            "Webhook için genel adres gerekli: Render'da RENDER_EXTERNAL_URL otomatik gelir, "
            "başka yerde STUDIO_PUBLIC_URL ayarla"
        )
    if settings.studio_store.strip().lower() == "db":
        await asyncio.to_thread(run_migrations)
    bot = StudioBot(settings)
    hook = StudioWebhook(bot, settings)
    await bot.bot.set_webhook(base + hook.path, secret_token=hook.secret)
    log.info("Telegram webhook set to %s%s", base, hook.path)
    await hook.serve("0.0.0.0", int(os.environ.get("PORT", "10000")))
