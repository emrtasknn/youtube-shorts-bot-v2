"""Narration -> timeline: every scene gets a start/end, every line a time slot."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.longform.spec import Film
from app.studio.models import Line, voice_key
from app.studio.tts import (
    SAMPLE_RATE,
    Audio,
    VoiceCast,
    apply_effect,
    level_clip,
    silence_bounds,
    synthesize,
)

LINE_GAP = 0.45  # pause between two lines of the same speaker
SPEAKER_GAP = 0.8  # pause when the speaker changes


@dataclass(slots=True)
class LineSlot:
    scene: int
    start: float
    end: float
    text: str  # caption text
    voice: str


@dataclass(slots=True)
class SceneSlot:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(slots=True)
class Timeline:
    scenes: list[SceneSlot]
    lines: list[LineSlot]
    voice: Audio
    used: str = ""
    clips: dict[int, Audio] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.scenes[-1].end if self.scenes else 0.0


async def speak(cast: VoiceCast, text: str, voice: str, cache: Path | None) -> Audio:
    """One levelled, effect-processed clip; cached on disk by role + text."""
    role = cast.role_for(Line(narration=text, voice=voice))
    key = hashlib.sha1(f"{role.name}|{role.tts.name}|{role.effect}|{text}".encode()).hexdigest()
    path = cache / f"{key[:16]}.npy" if cache else None
    if path is not None and path.is_file():
        return np.asarray(np.load(path), dtype=np.float32)
    syn = await synthesize(role.tts, text)
    a, b = silence_bounds(syn.audio)
    clip = level_clip(apply_effect(syn.audio[a:b], role.effect), gain_db=role.gain_db)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, clip)
    return clip


async def build_timeline(film: Film, cast: VoiceCast, *, cache: Path | None = None) -> Timeline:
    cast.check([Line(narration=s.text, voice=s.voice) for sc in film.scenes for s in sc.say])
    t = 0.0
    scenes: list[SceneSlot] = []
    lines: list[LineSlot] = []
    placed: list[tuple[float, Audio]] = []
    prev_voice: str | None = None
    for si, sc in enumerate(film.scenes):
        start = t
        if sc.say:
            t += sc.pad[0]
            for li, s in enumerate(sc.say):
                v = voice_key(s.voice)
                if li > 0:
                    t += SPEAKER_GAP if v != prev_voice else LINE_GAP
                clip = await speak(cast, s.text, s.voice, cache)
                dur = len(clip) / SAMPLE_RATE
                placed.append((t, clip))
                lines.append(LineSlot(si, round(t, 3), round(t + dur, 3), s.caption, v))
                t += dur
                prev_voice = v
            t += sc.pad[1]
        t = max(t, start + sc.hold)
        scenes.append(SceneSlot(round(start, 3), round(t, 3)))
    voice = np.zeros(int(t * SAMPLE_RATE) + SAMPLE_RATE, np.float32)
    for at, clip in placed:
        i = int(at * SAMPLE_RATE)
        voice[i : i + len(clip)] += clip[: len(voice) - i]
    return Timeline(scenes, lines, voice[: int(t * SAMPLE_RATE)], cast.used)


# ------------------------------------------------------------------ captions
def _chunks(text: str, limit: int = 84) -> list[str]:
    """Split a caption at sentence / clause marks into pieces of at most ``limit`` chars."""
    words, out, cur = text.split(), [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if len(cand) > limit and cur:
            out.append(cur)
            cur = w
        else:
            cur = cand
            if w.endswith((".", "?", "!", ";", ":")) and len(cur) > limit * 0.5:
                out.append(cur)
                cur = ""
    if cur:
        out.append(cur)
    return out


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(timeline: Timeline) -> str:
    """Closed captions; long lines are split and timed by character count."""
    rows: list[str] = []
    n = 0
    for ln in timeline.lines:
        parts = _chunks(ln.text)
        total = sum(len(p) for p in parts) or 1
        t = ln.start
        for p in parts:
            d = (ln.end - ln.start) * len(p) / total
            n += 1
            rows.append(f"{n}\n{_ts(t)} --> {_ts(t + d)}\n{p}\n")
            t += d
    return "\n".join(rows)


def chapters(film: Film, timeline: Timeline, intro: str = "Giriş") -> list[tuple[float, str]]:
    """YouTube chapter marks: the intro at 0:00 plus every chapter card."""
    marks = [(0.0, intro)]
    for sc, slot in zip(film.scenes, timeline.scenes, strict=True):
        if sc.kind == "chapter":
            marks.append((slot.start, sc.title))
    return marks


def fmt_mark(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m}:{s:02d}"
