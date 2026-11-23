"""Download Wikimedia Commons images (standard thumbnail sizes) with licence metadata.

    python scripts/commons_fetch.py docs/longform/vecihi-hurkus/commons_request.json

Request file::

    {"out": "img", "credits": "credits.json",
     "files": {"dh9": "De Havilland DH 9.jpg", "ismet": "~search words"}}

A value starting with ``~`` is searched (first file result). Images already in
``credits.json`` are skipped. Only Commons' standard thumbnail widths are requested
(see https://w.wiki/GHai), which is what Wikimedia asks automated clients to do.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

API = "https://commons.wikimedia.org/w/api.php"
UA = "BirGaripTarih-longform/1.0 (https://github.com/emrtasknn/youtube-shorts-bot-v2)"
STANDARD = (250, 330, 500, 960, 1280, 1920)


def _strip(s: str | None) -> str:
    return html.unescape(re.sub("<[^>]+>", "", s or "")).strip()


def api(client: httpx.Client, **params: Any) -> dict[str, Any]:
    params["format"] = "json"
    for attempt in range(6):
        r = client.get(API, params=params)
        if r.status_code == 200:
            data: dict[str, Any] = r.json()
            return data
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Commons API {r.status_code}")


def fetch(client: httpx.Client, title: str, dest_stem: Path) -> dict[str, str]:
    if title.startswith("~"):
        hits = api(
            client, action="query", list="search", srsearch=title[1:], srnamespace=6, srlimit=1
        )
        title = hits["query"]["search"][0]["title"][5:]
    info = api(
        client, action="query", titles="File:" + title, prop="imageinfo", iiprop="size|extmetadata"
    )
    ii = next(iter(info["query"]["pages"].values()))["imageinfo"][0]
    meta = ii.get("extmetadata", {})
    width = max([w for w in STANDARD if w <= ii["width"]] or [STANDARD[0]])
    thumb = api(
        client,
        action="query",
        titles="File:" + title,
        prop="imageinfo",
        iiprop="url",
        iiurlwidth=width,
    )
    url = next(iter(thumb["query"]["pages"].values()))["imageinfo"][0]["thumburl"]
    ext = url.rsplit(".", 1)[-1].lower()
    ext = ext if ext in ("jpg", "jpeg", "png") else "jpg"
    dest = dest_stem.with_suffix("." + ext)
    for attempt in range(6):
        r = client.get(url)
        if r.status_code == 200:
            dest.write_bytes(r.content)
            break
        time.sleep(15 * (attempt + 1))
    else:
        raise RuntimeError(f"{title}: HTTP {r.status_code}")
    return {
        "file": title,
        "path": f"{dest.parent.name}/{dest.name}",
        "license": _strip(meta.get("LicenseShortName", {}).get("value")),
        "artist": _strip(meta.get("Artist", {}).get("value"))[:120],
        "date": _strip(meta.get("DateTimeOriginal", {}).get("value"))[:40],
        "page": "https://commons.wikimedia.org/wiki/File:" + title.replace(" ", "_"),
        "http": "200",
    }


def main(request_path: Path) -> int:
    req = json.loads(request_path.read_text(encoding="utf-8"))
    root = request_path.parent
    out = root / req.get("out", "img")
    out.mkdir(parents=True, exist_ok=True)
    cpath = root / req.get("credits", "credits.json")
    credits = json.loads(cpath.read_text(encoding="utf-8")) if cpath.is_file() else {}
    failed = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True) as client:
        for key, title in req["files"].items():
            if key in credits:
                continue
            try:
                credits[key] = fetch(client, title, out / key)
                print(f"✓ {key}: {credits[key]['file']} ({credits[key]['license']})", flush=True)
            except Exception as exc:  # keep going; report at the end
                failed.append(key)
                print(f"✗ {key}: {exc}", flush=True)
            cpath.write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
            time.sleep(2)
    print(f"bitti; başarısız: {failed}" if failed else "bitti")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
