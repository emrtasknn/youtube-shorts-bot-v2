"""Film spec -> narration -> frames -> mp4 + captions + chapter list.

python -m app.longform docs/longform/vecihi-hurkus/film.json out/vecihi
python -m app.longform film.json out --still 12.5      # one frame as PNG
python -m app.longform film.json out --scale 0.5       # quick 960x540 draft
"""

from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.longform.frames import FilmFrames
from app.longform.sound import loudnorm, mix
from app.longform.spec import Film
from app.longform.timeline import Timeline, build_timeline, chapters, fmt_mark, to_srt
from app.studio.tts import VoiceCast

_FRAMES: FilmFrames | None = None


@dataclass(slots=True)
class FilmOutput:
    video: Path
    srt: Path
    description: Path
    duration: float
    voices: str


def _encode(job: tuple[int, int, int, str]) -> str:
    """Worker: frames [f0, f1) of the film to one mp4 segment."""
    f0, f1, fps, path = job
    fr = _FRAMES
    assert fr is not None
    tmp = path + ".part.mp4"
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{fr.W}x{fr.H}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-preset",
            "medium",
            "-tune",
            "film",
            "-pix_fmt",
            "yuv420p",
            str(tmp),
        ],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin is not None
    for fi in range(f0, f1):
        frame = fr.frame(fi / fps, fi)
        proc.stdin.write((frame * 255 + 0.5).astype(np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg segment failed: {path}")
    os.replace(tmp, path)
    return path


def scaled(film: Film, scale: float) -> Film:
    if scale == 1.0:
        return film
    w = int(film.width * scale) // 2 * 2
    h = int(film.height * scale) // 2 * 2
    return Film(film.title, film.scenes, film.root, w, h, film.fps)


async def narrate(film: Film, cast: VoiceCast, workdir: Path) -> Timeline:
    return await build_timeline(film, cast, cache=workdir / "tts-cache")


def still(film: Film, tl: Timeline, t: float, dest: Path) -> Path:
    fr = FilmFrames(film, tl)
    frame = fr.frame(t, int(t * film.fps))
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), (frame * 255 + 0.5).astype(np.uint8))
    return dest


def description(film: Film, tl: Timeline, credits: list[str], intro: str = "Giriş") -> str:
    marks = "\n".join(f"{fmt_mark(t)} {title}" for t, title in chapters(film, tl, intro))
    lines = [film.title, "", "Bölümler", marks]
    if credits:
        lines += ["", "Görseller", *credits]
    return "\n".join(lines) + "\n"


def render_film(
    film: Film,
    tl: Timeline,
    out: Path,
    *,
    workers: int | None = None,
    credits: list[str] | None = None,
    name: str = "film",
) -> FilmOutput:
    global _FRAMES
    out.mkdir(parents=True, exist_ok=True)
    seg_dir = out / "segments"
    seg_dir.mkdir(exist_ok=True)
    for old in seg_dir.glob("*.mp4"):
        old.unlink()

    raw_wav, wav = out / "mix_raw.wav", out / "mix.wav"
    mix(film, tl, raw_wav)
    loudnorm(raw_wav, wav)

    _FRAMES = FilmFrames(film, tl)
    fps = film.fps
    total_frames = int(round(tl.duration * fps))
    chunk = fps * 20  # 20-second segments keep every worker busy
    jobs = [
        (f0, min(f0 + chunk, total_frames), fps, str(seg_dir / f"{i:04d}.mp4"))
        for i, f0 in enumerate(range(0, total_frames, chunk))
    ]
    n = workers or max(1, (os.cpu_count() or 2))
    ctx = mp.get_context("fork")
    with ctx.Pool(n) as pool:
        for done, _ in enumerate(pool.imap(_encode, jobs), 1):
            print(f"  video {done}/{len(jobs)}", flush=True)

    concat = out / "segments.txt"
    concat.write_text("".join(f"file '{j[3]}'\n" for j in jobs), encoding="utf-8")
    video = out / f"{name}.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-i",
            str(wav),
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
        ],
        check=True,
    )
    srt = out / f"{name}.tr.srt"
    srt.write_text(to_srt(tl), encoding="utf-8")
    desc = out / "description.txt"
    desc.write_text(description(film, tl, credits or []), encoding="utf-8")
    (out / "timeline.json").write_text(
        json.dumps(
            {
                "duration": tl.duration,
                "scenes": [[s.start, s.end] for s in tl.scenes],
                "lines": [[ln.start, ln.end, ln.voice, ln.text] for ln in tl.lines],
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return FilmOutput(video, srt, desc, tl.duration, tl.used)


def run(film: Film, cast: VoiceCast, out: Path, **kw: object) -> FilmOutput:
    tl = asyncio.run(narrate(film, cast, out))
    return render_film(film, tl, out, **kw)  # type: ignore[arg-type]
