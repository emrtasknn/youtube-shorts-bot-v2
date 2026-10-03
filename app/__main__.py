from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from sqlalchemy.orm import Session

from app.application.services.telegram_control import TelegramControlPlane
from app.application.services.telegram_worker import TelegramWorker
from app.application.use_cases.generate_custom_short import (
    CustomShortRequest,
    GenerateCustomShort,
)
from app.config.settings import get_settings
from app.infrastructure.database.connection import get_session
from app.infrastructure.providers.youtube import YouTubePublisher
from app.infrastructure.telegram.bot import TelegramBot
from app.runtime import build_runtime


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YouTube Shorts Bot V2 runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    custom = subparsers.add_parser("custom", help="Generate one custom Short")
    custom.add_argument("topic", help="Topic for the Short")
    custom.add_argument("--run-key", default=None, help="Optional unique run key")
    custom.add_argument("--language", default="tr")
    custom.add_argument("--requested-by", default="cli")

    subparsers.add_parser(
        "telegram-review",
        help="Send all pending Shorts to the Telegram admin for review",
    )
    subparsers.add_parser(
        "telegram-poll",
        help="Run the Telegram approval and publishing worker",
    )
    return parser


def _build_telegram_bot() -> TelegramBot:
    settings = get_settings()
    return TelegramBot(
        settings.telegram_bot_token,
        timeout_seconds=settings.telegram_timeout_seconds,
    )


def _build_telegram_control(
    *,
    with_runtime: bool = False,
) -> tuple[TelegramControlPlane, TelegramBot, Session]:
    settings = get_settings()
    bot = _build_telegram_bot()
    session = get_session()

    if not with_runtime:
        return TelegramControlPlane(session=session, bot=bot), bot, session

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
    return control, bot, session


async def _run_custom(args: argparse.Namespace) -> None:
    settings = get_settings()
    runtime = build_runtime(settings)
    session = get_session()
    try:
        run_key = args.run_key or f"manual-{uuid.uuid4().hex}"
        result = await GenerateCustomShort(
            session=session,
            text=runtime.text,
            stock_media=runtime.stock_media,
            tts=runtime.tts,
            video_engine=runtime.video_engine,
            downloader=runtime.downloader,
        ).execute(
            CustomShortRequest(
                topic=args.topic,
                run_key=run_key,
                language=args.language,
                requested_by=args.requested_by,
            )
        )
        print(
            json.dumps(
                {
                    "run_id": str(result.run_id),
                    "content_id": str(result.content_id),
                    "script_id": str(result.script_id),
                    "output_path": str(result.output_path),
                    "duration_seconds": result.duration_seconds,
                    "status": result.status.value,
                },
                ensure_ascii=False,
            )
        )
    finally:
        session.close()


async def _run_telegram_review() -> None:
    settings = get_settings()
    control, bot, session = _build_telegram_control()
    try:
        worker = TelegramWorker(
            session=session,
            bot=bot,
            control=control,
            admin_chat_id=settings.telegram_admin_chat_id,
            admin_user_id=settings.telegram_admin_user_id,
        )
        sent = await worker.send_pending()
        print(json.dumps({"sent": sent}))
    finally:
        session.close()


async def _run_telegram_poll() -> None:
    settings = get_settings()
    control, bot, session = _build_telegram_control(with_runtime=True)
    try:
        worker = TelegramWorker(
            session=session,
            bot=control._bot,
            control=control,
            admin_chat_id=settings.telegram_admin_chat_id,
            admin_user_id=settings.telegram_admin_user_id,
        )
        await worker.run_forever()
    finally:
        session.close()


async def _run(args: argparse.Namespace) -> None:
    if args.command == "custom":
        await _run_custom(args)
    elif args.command == "telegram-review":
        await _run_telegram_review()
    elif args.command == "telegram-poll":
        await _run_telegram_poll()


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
