from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from app.application.use_cases.generate_custom_short import (
    CustomShortRequest,
    GenerateCustomShort,
)
from app.config.settings import get_settings
from app.infrastructure.database.connection import get_session
from app.runtime import build_runtime


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YouTube Shorts Bot V2 runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    custom = subparsers.add_parser("custom", help="Generate one custom Short")
    custom.add_argument("topic", help="Topic for the Short")
    custom.add_argument("--run-key", default=None, help="Optional unique run key")
    custom.add_argument("--language", default="tr")
    custom.add_argument("--requested-by", default="cli")
    return parser


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


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(_run_custom(args))


if __name__ == "__main__":
    main()
