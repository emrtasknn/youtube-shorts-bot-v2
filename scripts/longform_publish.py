"""Upload a rendered long-form film to YouTube as PRIVATE (thumbnail + Turkish captions).

    YOUTUBE_CLIENT_ID=... YOUTUBE_CLIENT_SECRET=... YOUTUBE_REFRESH_TOKEN=... \
    python scripts/longform_publish.py docs/longform/vecihi-hurkus/render_request.json out/

The video stays private: making it public is a deliberate step in YouTube Studio.
Writes ``<request dir>/published.json`` with the video id and any warnings.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

from app.studio.models import Project
from app.studio.publisher import UPLOAD_API, StudioYouTube


async def upload_captions(yt: StudioYouTube, video_id: str, srt: Path, name: str) -> str:
    """Attach the SRT as the Turkish caption track; returns a warning or ''."""
    token = await yt._token()
    meta = {"snippet": {"videoId": video_id, "language": "tr", "name": name, "isDraft": False}}
    boundary = "longform-captions"
    body = (
        (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + srt.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{UPLOAD_API}/captions",
            params={"part": "snippet", "uploadType": "multipart"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            content=body,
        )
    return (
        "" if r.status_code < 400 else f"Altyazı yüklenemedi (HTTP {r.status_code}): {r.text[:200]}"
    )


async def main(request_path: Path, out: Path) -> int:
    req = json.loads(request_path.read_text(encoding="utf-8"))
    film = json.loads(Path(req["film"]).read_text(encoding="utf-8"))
    name = req.get("name", "film")
    video, srt = out / f"{name}.mp4", out / f"{name}.tr.srt"
    desc_lines = (out / "description.txt").read_text(encoding="utf-8").splitlines()[1:]
    description = "\n".join([req.get("intro", ""), *desc_lines]).strip()
    if req.get("disclosure"):
        description += "\n\n" + req["disclosure"]
    project = Project(
        topic=film.get("title", name),
        title=req.get("title") or film.get("title", name),
        description=description[:4900],
        tags=req.get("tags", []),
    )
    yt = StudioYouTube(
        os.environ["YOUTUBE_CLIENT_ID"],
        os.environ["YOUTUBE_CLIENT_SECRET"],
        os.environ["YOUTUBE_REFRESH_TOKEN"],
        category_id=str(req.get("category_id", "27")),
    )
    thumb = Path(req["thumbnail"]) if req.get("thumbnail") else None
    res = await yt.upload_private(project, video, thumb)
    warnings = list(res.warnings)
    if srt.is_file():
        w = await upload_captions(yt, res.video_id, srt, "Türkçe")
        if w:
            warnings.append(w)
    record = {
        "video_id": res.video_id,
        "url": f"https://www.youtube.com/watch?v={res.video_id}",
        "privacy": "private",
        "warnings": warnings,
    }
    (request_path.parent / "published.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(Path(sys.argv[1]), Path(sys.argv[2]))))
