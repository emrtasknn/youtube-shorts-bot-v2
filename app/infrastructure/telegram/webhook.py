from __future__ import annotations

import asyncio
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.application.services.telegram_control import TelegramControlPlane
from app.application.services.telegram_worker import TelegramWorker
from app.application.use_cases.generate_custom_short import GenerateCustomShort
from app.config.settings import get_settings
from app.infrastructure.database.connection import get_session
from app.infrastructure.providers.youtube import YouTubePublisher
from app.infrastructure.telegram.bot import TelegramBot
from app.runtime import build_runtime


def _build_worker() -> TelegramWorker:
    settings = get_settings()
    session = get_session()
    bot = TelegramBot(settings.telegram_bot_token, timeout_seconds=settings.telegram_timeout_seconds)
    runtime = build_runtime(settings)
    generator = GenerateCustomShort(
        session=session,
        text=runtime.text,
        stock_media=runtime.stock_media,
        tts=runtime.tts,
        video_engine=runtime.video_engine,
        downloader=runtime.downloader,
    )
    publisher = YouTubePublisher(
        settings.youtube_client_id,
        settings.youtube_client_secret,
        settings.youtube_refresh_token,
    )
    control = TelegramControlPlane(
        session=session,
        bot=bot,
        publisher=publisher,
        generator=generator,
    )
    return TelegramWorker(
        session=session,
        bot=bot,
        control=control,
        admin_chat_id=settings.telegram_admin_chat_id,
        admin_user_id=settings.telegram_admin_user_id,
    )


def _process(update: dict[str, object]) -> None:
    worker = _build_worker()
    try:
        asyncio.run(worker.handle_update(update))
    finally:
        worker._session.close()


class WebhookHandler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"ok": True, "service": "youtube-shorts-bot-v2"})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        settings = get_settings()
        if self.path != settings.telegram_webhook_path:
            self._json(404, {"error": "not_found"})
            return

        expected = settings.telegram_webhook_secret
        supplied = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if expected and not hmac.compare_digest(supplied, expected):
            self._json(401, {"error": "unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            update = json.loads(self.rfile.read(length).decode("utf-8"))
            threading.Thread(target=_process, args=(update,), daemon=True).start()
            self._json(200, {"ok": True})
        except (TypeError, ValueError, json.JSONDecodeError):
            self._json(400, {"ok": False})

    def log_message(self, format: str, *args: object) -> None:
        return


def run() -> None:
    settings = get_settings()
    bot = TelegramBot(settings.telegram_bot_token, timeout_seconds=settings.telegram_timeout_seconds)
    public_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not public_url:
        raise RuntimeError("RENDER_EXTERNAL_URL is required for Telegram webhook")
    webhook_url = public_url + settings.telegram_webhook_path
    asyncio.run(bot.set_webhook(webhook_url, secret_token=settings.telegram_webhook_secret))
    server = ThreadingHTTPServer(
        ("0.0.0.0", int(os.environ.get("PORT", "10000"))),
        WebhookHandler,
    )
    server.serve_forever()
