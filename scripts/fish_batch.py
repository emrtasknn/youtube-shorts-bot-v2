"""Synthesize a batch of lines with Fish Audio (run where api.fish.audio is reachable).

    FISH_AUDIO_API_KEY=... python scripts/fish_batch.py docs/longform/vecihi-hurkus/fish_request.json

Request file::

    {"out": "fish",                       # output folder next to the request
     "model": "s2.1-pro-free",
     "voices": ["<reference_id>", ...],   # explicit Fish voice models, and/or
     "search": {"language": "tr", "limit": 3, "title": ""},   # top community voices
     "lines": [{"id": "ceza1", "text": "İzinsiz uçuş."}]}

Every voice reads every line: ``<out>/<voice>/<id>.wav``. ``<out>/manifest.json``
lists the voices (title, languages, popularity) and the files, so a person can pick
one and the long-form renderer can use the files directly (``FileTTS``).

``search`` returns community voices as *candidates only*. Many of them are clones of
real people (politicians, actors); never put such a voice in a film. Pin the chosen
generic voice in ``voices`` and drop ``search`` before the final batch.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

API = "https://api.fish.audio"


def search_voices(client: httpx.Client, spec: dict[str, Any]) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "page_size": int(spec.get("limit", 3)) * 4,
        "page_number": 1,
        "sort_by": spec.get("sort_by", "score"),
    }
    if spec.get("language"):
        params["language"] = spec["language"]
    if spec.get("title"):
        params["title"] = spec["title"]
    r = client.get(f"{API}/model", params=params)
    r.raise_for_status()
    items = r.json().get("items", [])
    out = []
    for it in items:
        langs = it.get("languages") or []
        if spec.get("language") and spec["language"] not in langs:
            continue
        out.append(
            {
                "id": it["_id"],
                "title": it.get("title", ""),
                "description": (it.get("description") or "")[:200],
                "languages": langs,
                "tags": it.get("tags", []),
                "likes": it.get("like_count", 0),
                "uses": it.get("task_count", 0),
            }
        )
        if len(out) >= int(spec.get("limit", 3)):
            break
    return out


def synth(client: httpx.Client, text: str, ref: str, model: str) -> bytes:
    payload: dict[str, Any] = {"text": text, "format": "wav", "normalize": True}
    if ref:
        payload["reference_id"] = ref
    for attempt in range(4):
        r = client.post(f"{API}/v1/tts", json=payload, headers={"model": model})
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Fish Audio HTTP {r.status_code}: {r.text[:300]}")
        return r.content
    raise RuntimeError("Fish Audio: too many retries")


def main(request_path: Path) -> int:
    key = os.environ.get("FISH_AUDIO_API_KEY", "")
    if not key:
        print("FISH_AUDIO_API_KEY yok", file=sys.stderr)
        return 2
    req = json.loads(request_path.read_text(encoding="utf-8"))
    out = request_path.parent / req.get("out", "fish")
    out.mkdir(parents=True, exist_ok=True)
    model = req.get("model", "s2.1-pro-free")
    headers = {"Authorization": f"Bearer {key}"}
    manifest: dict[str, Any] = {"model": model, "voices": [], "files": {}}
    with httpx.Client(headers=headers, timeout=120) as client:
        voices = [{"id": v, "title": ""} for v in req.get("voices", [])]
        if req.get("search"):
            try:
                voices += search_voices(client, req["search"])
            except httpx.HTTPError as exc:
                print(f"ses arama başarısız: {exc}", file=sys.stderr)
        if not voices:
            voices = [{"id": "", "title": "default"}]
        manifest["voices"] = voices
        for v in voices:
            vdir = out / (v["id"] or "default")
            vdir.mkdir(exist_ok=True)
            for line in req["lines"]:
                dest = vdir / f"{line['id']}.wav"
                if not dest.is_file():
                    dest.write_bytes(synth(client, line["text"], v["id"], model))
                    print(f"✓ {v['title'] or v['id']}: {line['id']}", flush=True)
                h = hashlib.sha1(line["text"].encode()).hexdigest()[:16]
                manifest["files"].setdefault(v["id"] or "default", {})[h] = dest.name
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(voices)} ses × {len(req['lines'])} satır → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
