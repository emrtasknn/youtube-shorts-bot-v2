"""Full channel analytics snapshot (YouTube Data + Analytics APIs) as one JSON file.

    YOUTUBE_CLIENT_ID=... YOUTUBE_CLIENT_SECRET=... YOUTUBE_REFRESH_TOKEN=... \
    python scripts/channel_report.py out/report.json [--days 90] [--retention 40]

Needs a refresh token with the ``yt-analytics.readonly`` scope (see
scripts/youtube_refresh_token.py). Every section is fetched independently: a failing
section is recorded under ``errors`` and the rest of the report still comes out.
The repository is public, so the workflow encrypts this file before committing it.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import httpx

from app.infrastructure.providers.youtube import YouTubePublisher

DATA = "https://www.googleapis.com/youtube/v3"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"

CORE = "views,engagedViews,estimatedMinutesWatched,averageViewDuration,averageViewPercentage"
SOCIAL = "subscribersGained,subscribersLost,likes,comments,shares"


class Client:
    def __init__(self, token: str) -> None:
        self.http = httpx.AsyncClient(timeout=60, headers={"Authorization": f"Bearer {token}"})

    async def data(self, path: str, **params: Any) -> dict[str, Any]:
        r = await self.http.get(f"{DATA}/{path}", params=params)
        r.raise_for_status()
        out: dict[str, Any] = r.json()
        return out

    async def report(self, **params: Any) -> dict[str, Any]:
        params = {"ids": "channel==MINE", **params}
        r = await self.http.get(ANALYTICS, params=params)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        body = r.json()
        cols = [h["name"] for h in body.get("columnHeaders", [])]
        return {"columns": cols, "rows": body.get("rows", [])}


async def videos(c: Client) -> list[dict[str, Any]]:
    ch = (await c.data("channels", part="contentDetails,snippet,statistics", mine="true"))["items"][
        0
    ]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids: list[str] = []
    token = ""
    while True:
        page = await c.data(
            "playlistItems",
            part="contentDetails",
            playlistId=uploads,
            maxResults=50,
            pageToken=token,
        )
        ids += [it["contentDetails"]["videoId"] for it in page.get("items", [])]
        token = page.get("nextPageToken", "")
        if not token:
            break
    out = []
    for i in range(0, len(ids), 50):
        page = await c.data(
            "videos", part="snippet,contentDetails,statistics,status", id=",".join(ids[i : i + 50])
        )
        for v in page.get("items", []):
            sn, cd, st = v["snippet"], v["contentDetails"], v.get("statistics", {})
            out.append(
                {
                    "id": v["id"],
                    "title": sn.get("title", ""),
                    "published": sn.get("publishedAt", ""),
                    "duration": cd.get("duration", ""),
                    "privacy": v.get("status", {}).get("privacyStatus", ""),
                    "views": int(st.get("viewCount", 0)),
                    "likes": int(st.get("likeCount", 0)),
                    "comments": int(st.get("commentCount", 0)),
                    "tags": sn.get("tags", [])[:15],
                }
            )
    return [{"channel": {"title": ch["snippet"]["title"], **ch.get("statistics", {})}}, *out]


async def build(days: int, retention_n: int) -> dict[str, Any]:
    token = await YouTubePublisher(
        os.environ["YOUTUBE_CLIENT_ID"],
        os.environ["YOUTUBE_CLIENT_SECRET"],
        os.environ["YOUTUBE_REFRESH_TOKEN"],
    )._access_token()
    c = Client(token)
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    span = {"startDate": start.isoformat(), "endDate": end.isoformat()}
    rep: dict[str, Any] = {
        "generated": dt.datetime.now(dt.UTC).isoformat(),
        "span": span,
        "errors": {},
    }

    async def section(name: str, coro: Any) -> None:
        try:
            rep[name] = await coro
        except Exception as exc:  # keep the rest of the report
            rep["errors"][name] = f"{type(exc).__name__}: {exc}"[:400]

    await section("videos", videos(c))
    await section("daily", c.report(**span, dimensions="day", metrics=f"{CORE},{SOCIAL}"))
    await section(
        "content_type",
        c.report(**span, dimensions="creatorContentType", metrics=f"{CORE},subscribersGained"),
    )
    await section(
        "per_video",
        c.report(
            **span,
            dimensions="video",
            metrics=f"{CORE},{SOCIAL}",
            sort="-views",
            maxResults=200,
        ),
    )
    await section(
        "traffic",
        c.report(**span, dimensions="insightTrafficSourceType", metrics=CORE, sort="-views"),
    )
    await section(
        "traffic_by_type",
        c.report(
            **span,
            dimensions="insightTrafficSourceType,creatorContentType",
            metrics="views,engagedViews,estimatedMinutesWatched",
        ),
    )
    await section("subscribed", c.report(**span, dimensions="subscribedStatus", metrics=CORE))
    await section("device", c.report(**span, dimensions="deviceType", metrics=CORE))
    await section(
        "country",
        c.report(**span, dimensions="country", metrics=CORE, sort="-views", maxResults=15),
    )
    await section(
        "age_gender", c.report(**span, dimensions="ageGroup,gender", metrics="viewerPercentage")
    )

    # per-video detail for the most recent uploads: retention curve + traffic sources
    vids = [v for v in rep.get("videos", [])[1:] if v.get("privacy") == "public"]
    vids.sort(key=lambda v: v["published"], reverse=True)
    detail: dict[str, Any] = {}
    for v in vids[:retention_n]:
        d: dict[str, Any] = {}
        vf = {"filters": f"video=={v['id']}"}
        since = {"startDate": v["published"][:10], "endDate": end.isoformat()}
        for key, params in (
            (
                "retention",
                dict(
                    dimensions="elapsedVideoTimeRatio",
                    metrics="audienceWatchRatio,relativeRetentionPerformance",
                ),
            ),
            ("traffic", dict(dimensions="insightTrafficSourceType", metrics=CORE)),
            ("summary", dict(metrics=f"{CORE},{SOCIAL}")),
        ):
            try:
                d[key] = await c.report(**since, **vf, **params)
            except Exception as exc:
                d[key] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        detail[v["id"]] = d
    rep["video_detail"] = detail
    await c.http.aclose()
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--retention", type=int, default=40)
    args = ap.parse_args()
    rep = asyncio.run(build(args.days, args.retention))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"rapor: {len(rep.get('videos', [])) - 1} video, hatalı bölümler: {list(rep['errors'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
