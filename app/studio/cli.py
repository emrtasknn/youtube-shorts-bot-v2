"""Studio commands.

python -m app studio-bot                         run the Telegram bot (long polling)
python -m app studio-webhook                     run the bot behind a Telegram webhook (free web hosts)
python -m app studio-render --project-file p.json [--no-upload] [--no-notify]
python -m app studio-render --payload <base64>   (used by GitHub Actions)
python -m app studio-script "konu"               print a script JSON (LLM test)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from app.config.settings import get_settings
from app.studio.models import Project


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m app", description="Studio V3")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("studio-bot", help="Run the Studio Telegram bot")
    sub.add_parser("studio-webhook", help="Run the Studio bot behind a Telegram webhook")
    r = sub.add_parser("studio-render", help="Render one project")
    src = r.add_mutually_exclusive_group(required=True)
    src.add_argument("--project-file")
    src.add_argument("--payload", help="base64 gzip project JSON (or env var name with @NAME)")
    r.add_argument("--no-upload", action="store_true")
    r.add_argument("--no-notify", action="store_true")
    r.add_argument("--tts", default="", help="override TTS chain, e.g. 'piper'")
    r.add_argument("--width", type=int, default=1080)
    s = sub.add_parser("studio-script", help="Write a script for a topic and print JSON")
    s.add_argument("topic")
    return ap


async def _amain(args: argparse.Namespace) -> None:
    settings = get_settings()
    if args.command == "studio-bot":
        from app.studio.bot import StudioBot

        await StudioBot(settings).run()
    elif args.command == "studio-webhook":
        from app.studio.webhook import run_webhook

        await run_webhook(settings)
    elif args.command == "studio-render":
        from app.studio.jobs import decode_payload, run_render_job

        if args.project_file:
            project = Project.from_json(Path(args.project_file).read_text(encoding="utf-8"))
        else:
            payload = args.payload
            if payload.startswith("@"):
                payload = os.environ[payload[1:]]
            project = decode_payload(payload)
        done = await run_render_job(
            project,
            settings,
            upload=not args.no_upload,
            notify=not args.no_notify,
            tts_override=args.tts,
            width=args.width,
        )
        print(json.dumps({"id": done.id, "status": done.status, "youtube_id": done.youtube_id}))
    elif args.command == "studio-script":
        from app.studio.factory import build_llm
        from app.studio.script_writer import ScriptWriter

        project = await ScriptWriter(build_llm(settings)).write(args.topic)
        print(project.to_json())


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    # httpx logs every request URL at INFO; Telegram URLs contain the bot token.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    asyncio.run(_amain(_parser().parse_args(argv)))
