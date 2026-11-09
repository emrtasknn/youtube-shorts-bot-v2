"""Wikimedia Commons candidates for visuals the user did not supply.

The bot never auto-picks: it shows the top candidates in Telegram and the human
taps the right one. Free archival sources are noisy; a 2-second human choice
beats any amount of automated verification.
"""

from __future__ import annotations

import html
import re
from typing import Any

import httpx

from app.studio.http import USER_AGENT
from app.studio.models import Candidate

API = "https://commons.wikimedia.org/w/api.php"
_BAD_TITLE = re.compile(r"(logo|icon|map|flag|coat of arms|signature|diagram|svg)", re.I)


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def parse_candidates(payload: dict[str, Any], *, min_side: int = 500) -> list[Candidate]:
    pages = (payload.get("query") or {}).get("pages") or []
    ranked: list[tuple[int, int, Candidate]] = []
    for page in pages:
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        title = str(page.get("title", "")).removeprefix("File:")
        mime = str(info.get("mime", ""))
        w, h = int(info.get("width") or 0), int(info.get("height") or 0)
        if mime not in ("image/jpeg", "image/png", "image/webp") or min(w, h) < min_side:
            continue
        if _BAD_TITLE.search(title):
            continue
        meta = info.get("extmetadata") or {}
        lic = _strip_html(str((meta.get("LicenseShortName") or {}).get("value", "")))
        artist = _strip_html(str((meta.get("Artist") or {}).get("value", "")))
        url = str(info.get("thumburl") or info.get("url") or "")
        thumb = str(info.get("thumburl") or url)
        if not url:
            continue
        cand = Candidate(
            url=url,
            thumb_url=thumb,
            title=title[:90],
            license=lic,
            attribution=f"{artist} — {lic}".strip(" —") if artist else lic,
        )
        ranked.append((int(page.get("index", 999)), -min(w, h), cand))
    ranked.sort(key=lambda r: (r[0], r[1]))
    return [c for _, _, c in ranked]


async def search_commons(query: str, *, limit: int = 3, timeout: float = 30.0) -> list[Candidate]:
    params: dict[str, str | int] = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": 6,
        "gsrlimit": 20,
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": 1600,
        "format": "json",
        "formatversion": 2,
    }
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
        r = await client.get(API, params=params)
        r.raise_for_status()
    return parse_candidates(r.json())[:limit]


_WORD = re.compile(r"[\wÇĞİÖŞÜçğıöşüÂâÎîÛû'’]+")


def search_terms(text: str) -> list[str]:
    """Commons queries to try for a visual, most specific first.

    A whole Turkish sentence ("Naaşı önce İstanbul'dan Yavuz zırhlısıyla İzmit'e
    taşındı.") finds nothing on Commons; its proper names and years do
    ("İstanbul Yavuz İzmit").
    """
    words = _WORD.findall(text)
    names: list[str] = []
    for i, w in enumerate(words):
        base = re.split(r"['’]", w)[0]
        if re.fullmatch(r"1[5-9]\d\d|20\d\d", base):
            names.append(base)
        elif (
            base[:1].isupper()
            and len(base) > 2
            and (
                i > 0
                or "'" in w
                or "’" in w
                or (len(words) > 1 and words[1][:1].isupper())  # "Dolmabahçe Sarayı"
            )
        ):
            names.append(base)
    queries: list[str] = []
    if len(words) <= 5:
        queries.append(" ".join(words))
    if names:
        queries.append(" ".join(dict.fromkeys(names)))
        queries.append(" ".join(list(dict.fromkeys(names))[:2]))
    if words and words[0][:1].isupper():
        queries.append(re.split(r"['’]", words[0])[0])
    if not queries and words:
        queries.append(" ".join(sorted(words, key=len, reverse=True)[:3]))
    return [q for q in dict.fromkeys(queries) if q.strip()]


async def search_commons_terms(queries: list[str], *, limit: int = 3) -> list[Candidate]:
    """Try each query until one finds candidates."""
    for q in queries:
        found = await search_commons(q, limit=limit)
        if found:
            return found
    return []


_FILE_PAGE = re.compile(r"^https?://commons\.wikimedia\.org/wiki/(?:File|Dosya):(.+)$", re.I)


def image_url(link: str) -> str:
    """A Commons file page link -> a direct image URL; other links unchanged."""
    m = _FILE_PAGE.match(link.strip())
    if m:
        return f"https://commons.wikimedia.org/wiki/Special:FilePath/{m.group(1)}"
    return link.strip()
