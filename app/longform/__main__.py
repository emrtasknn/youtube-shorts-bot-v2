"""CLI for the long-form renderer (see ``render.py`` for examples)."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.config.settings import Settings
from app.longform.render import narrate, render_film, scaled, still
from app.longform.spec import load_film
from app.longform.timeline import fmt_mark
from app.studio.factory import build_cast


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m app.longform")
    ap.add_argument("spec", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--scale", type=float, default=1.0, help="0.5 = 960x540 draft")
    ap.add_argument("--still", type=float, action="append", default=[], help="PNG at second(s)")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--name", default="film")
    ap.add_argument("--credits", type=Path, help="JSON list of credit lines for the description")
    args = ap.parse_args(argv)

    film = scaled(load_film(args.spec), args.scale)
    cast = build_cast(Settings())
    print(f"🎙 {cast.name}", flush=True)
    tl = asyncio.run(narrate(film, cast, args.out))
    print(f"⏱ {fmt_mark(tl.duration)} ({tl.duration:.1f} sn) · {len(tl.lines)} satır", flush=True)
    if args.still:
        for t in args.still:
            print(still(film, tl, t, args.out / f"still_{t:07.2f}.png"))
        return
    credits = json.loads(args.credits.read_text(encoding="utf-8")) if args.credits else []
    res = render_film(
        film, tl, args.out, workers=args.workers or None, credits=credits, name=args.name
    )
    print(f"✅ {res.video} · {fmt_mark(res.duration)} · {res.voices}")


if __name__ == "__main__":
    main()
