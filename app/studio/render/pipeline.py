"""End-to-end render: project -> voice -> shots -> video + mix -> mp4 + thumbnails."""

from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import os
import re
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np

from app.studio.align import Aligner
from app.studio.http import USER_AGENT
from app.studio.models import Project
from app.studio.render.audio import SoundDesigner, mix, write_wav
from app.studio.render.engine import FrameRenderer, encode_shot, prepare_visuals
from app.studio.render.planner import plan_shots
from app.studio.render.thumbnail import make_thumbnail
from app.studio.tts import SAMPLE_RATE, TTSBackend, build_voice_track

TelegramDownloader = Callable[[str, Path], Awaitable[Path]]
TELEGRAM_VIDEO_LIMIT = 48 * 1024 * 1024


@dataclass(slots=True)
class RenderOutput:
    video: Path
    preview: Path
    thumb_vertical: Path
    thumb_horizontal: Path
    duration: float
    tts_used: str
    alignment: str = "syllable"


async def fetch_visual(source: str, dest: Path, telegram: TelegramDownloader | None) -> Path:
    kind, _, ref = source.partition(":")
    if kind == "file":
        return Path(ref)
    if kind == "telegram":
        if telegram is None:
            raise RuntimeError("Telegram görseli için bot token gerekli")
        return await telegram(ref, dest)
    if kind == "url":
        dest.write_bytes(await download_image(ref))
        return dest
    raise ValueError(f"Bilinmeyen görsel kaynağı: {source}")


class VisualFetchError(RuntimeError):
    """A visual could not be downloaded; the message tells the user what to do."""


_THUMB = re.compile(r"^(https://[^/]+/wikipedia/[^/]+)/thumb/(\w/\w\w/[^/]+)/[^/]+$")
_RETRY_STATUS = (403, 429, 500, 502, 503, 504)


def original_of_thumb(url: str) -> str | None:
    """Wikimedia thumbnail URL -> the original file on upload.wikimedia.org."""
    m = _THUMB.match(url.split("?", 1)[0])
    if not m:
        return None
    path = m.group(1).split("/wikipedia/", 1)[1]
    return f"https://upload.wikimedia.org/wikipedia/{path}/{m.group(2)}"


async def download_image(
    url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    pause: float = 2.0,
) -> bytes:
    """GET an image with a proper User-Agent; retry once on throttling, then try the original."""
    candidates = [url.split("?", 1)[0]]
    original = original_of_thumb(url)
    if original:
        candidates.append(original)
    last = ""
    async with httpx.AsyncClient(
        timeout=60, follow_redirects=True, headers={"User-Agent": USER_AGENT}, transport=transport
    ) as client:
        for target in candidates:
            for attempt in range(2):
                try:
                    r = await client.get(target)
                except httpx.HTTPError as exc:
                    last = f"{type(exc).__name__}"
                    break
                if r.status_code < 400 and r.content:
                    return r.content
                last = f"HTTP {r.status_code}"
                if r.status_code not in _RETRY_STATUS or attempt:
                    break
                try:
                    wait = float(r.headers.get("retry-after", pause))
                except ValueError:
                    wait = pause
                await asyncio.sleep(min(wait, 10.0))
    raise VisualFetchError(last or "boş yanıt")


_RENDERER: FrameRenderer | None = None
_TOTAL = 0.0


def _render_one(args: tuple[int, str]) -> int:
    assert _RENDERER is not None
    return encode_shot(_RENDERER, args[0], Path(args[1]), _TOTAL)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


async def render_project(
    project: Project,
    workdir: Path,
    tts: TTSBackend,
    *,
    telegram: TelegramDownloader | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    workers: int | None = None,
    progress: Callable[[str], Awaitable[None]] | None = None,
    aligner: Aligner | None = None,
) -> RenderOutput:
    global _RENDERER, _TOTAL

    async def say(msg: str) -> None:
        if progress is not None:
            await progress(msg)

    problems = project.validate()
    if problems:
        raise ValueError(" ".join(problems))
    missing = project.missing_visuals()
    if missing:
        raise ValueError("Eksik görseller: " + ", ".join(str(i + 1) for i in missing))

    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    img_dir = workdir / "images"
    img_dir.mkdir(exist_ok=True)
    shots_dir = workdir / "shots"
    shots_dir.mkdir(exist_ok=True)
    for old in shots_dir.glob("*.mp4"):
        old.unlink()

    await say("🖼 Görseller indiriliyor")
    used = sorted({ln.visual for ln in project.lines if not ln.card})
    paths: dict[int, Path] = {}
    for i in used:
        try:
            paths[i] = await fetch_visual(
                project.visuals[i].source, img_dir / f"{i + 1}.jpg", telegram
            )
        except (VisualFetchError, httpx.HTTPError) as exc:
            raise VisualFetchError(
                f"g{i + 1} ({project.visuals[i].description[:60]}) indirilemedi: {exc}. "
                f"Bu görsel için fotoğraf gönder (açıklamaya {i + 1} yaz) ya da 🔎 ile başka "
                "aday seç, sonra Tekrar dene."
            ) from exc
    focus = {i: (project.visuals[i].focus_x, project.visuals[i].focus_y) for i in used}
    visuals = prepare_visuals(paths, focus)

    await say(f"🎙 Seslendirme ({tts.name})")
    voice = await build_voice_track(project.lines, tts, aligner=aligner)
    if aligner is not None:
        await say(f"⏱ Kelime hizalama: {voice.alignment}")
    total = voice.duration
    voice_wav = workdir / "voice.wav"
    write_wav(voice_wav, voice.audio, SAMPLE_RATE)

    shots = plan_shots(project, voice.lines, voice.words, visuals.info, total)
    (workdir / "timeline.json").write_text(
        json.dumps(
            {
                "duration": total,
                "shots": [
                    {
                        "start": s.start,
                        "end": s.end,
                        "line": s.line,
                        "visual": s.visual,
                        "mode": s.mode,
                    }
                    for s in shots
                ],
                "words": [[w.word, w.start, w.end] for w in voice.words],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    await say(f"🎵 Müzik ve efektler · {len(shots)} plan")
    sd = SoundDesigner()
    card_times = [s.start for s in shots if s.mode == "title"]
    write_wav(
        workdir / "music.wav", sd.music(total + 0.15, card_times, [s.start for s in shots]) * 0.6
    )
    write_wav(workdir / "sfx.wav", sd.sfx(total + 0.15, shots) * 0.8)
    mix_wav = workdir / "mix.wav"
    mix(voice_wav, workdir / "music.wav", workdir / "sfx.wav", mix_wav)

    await say("🎬 Kurgu render ediliyor")
    _RENDERER = FrameRenderer(shots, voice.words, visuals, width=width, height=height, fps=fps)
    _TOTAL = total
    jobs = [(i, str(shots_dir / f"s{i:03d}.mp4")) for i in range(len(shots))]
    n_workers = workers or min(os.cpu_count() or 2, 4)
    if n_workers > 1 and "fork" in mp.get_all_start_methods():
        with mp.get_context("fork").Pool(n_workers) as pool:
            pool.map(_render_one, jobs)
    else:
        for job in jobs:
            _render_one(job)

    concat = workdir / "concat.txt"
    concat.write_text("".join(f"file '{p}'\n" for _, p in jobs), encoding="utf-8")
    silent = workdir / "video_only.mp4"
    _ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent))
    video = workdir / "final.mp4"
    _ffmpeg(
        "-i",
        str(silent),
        "-i",
        str(mix_wav),
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(video),
    )

    preview = workdir / "preview.mp4"
    _ffmpeg(
        "-i",
        str(video),
        "-vf",
        "scale=720:1280",
        "-c:v",
        "libx264",
        "-crf",
        "27",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(preview),
    )
    if preview.stat().st_size > TELEGRAM_VIDEO_LIMIT:
        _ffmpeg(
            "-i",
            str(video),
            "-vf",
            "scale=540:960",
            "-c:v",
            "libx264",
            "-crf",
            "30",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            str(preview),
        )

    await say("🖌 Thumbnail")
    tv = project.thumbnail_visual if project.thumbnail_visual in paths else used[0]
    label = next((ln.kicker for ln in project.lines if ln.kicker), "")
    text = project.thumbnail_text or project.title
    fpt = (visuals.info[tv].focus_x, visuals.info[tv].focus_y)
    thumb_v = make_thumbnail(
        paths[tv],
        text,
        workdir / "thumb_vertical.jpg",
        width=1080,
        height=1920,
        label=label,
        focus=fpt,
    )
    thumb_h = make_thumbnail(
        paths[tv],
        text,
        workdir / "thumb_horizontal.jpg",
        width=1280,
        height=720,
        label=label,
        focus=fpt,
    )
    return RenderOutput(
        video,
        preview,
        thumb_v,
        thumb_h,
        float(np.round(total, 2)),
        getattr(tts, "used", "") or tts.name,
        voice.alignment,
    )
