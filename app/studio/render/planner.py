"""Shot planning: narration timing + visuals -> a list of camera moves."""

from __future__ import annotations

from dataclasses import dataclass

from app.studio.models import Era, Project
from app.studio.text import WordTiming
from app.studio.tts import LineTiming

MAX_SHOT_SECONDS = 4.2


@dataclass(frozen=True, slots=True)
class ImageInfo:
    width: int
    height: int
    focus_x: float = 0.5
    focus_y: float = 0.45

    @property
    def aspect(self) -> float:
        return self.width / max(self.height, 1)


@dataclass(frozen=True, slots=True)
class Move:
    cx: float
    cy: float
    zoom: float


@dataclass(frozen=True, slots=True)
class Shot:
    start: float
    end: float
    line: int
    visual: int  # -1 for card shots
    mode: str  # "bleed" | "card" | "title"
    a: Move
    b: Move
    era: Era
    kicker: str
    card_text: str = ""
    new_visual: bool = True

    @property
    def duration(self) -> float:
        return self.end - self.start


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return min(max(v, lo), hi)


def _moves(info: ImageInfo, pattern: int, detail: bool) -> tuple[Move, Move]:
    fx, fy = info.focus_x, info.focus_y
    if detail:  # punch-in on the subject
        z0, z1 = 1.5, 1.75
        if pattern % 2:
            z0, z1 = z1, z0 - 0.1
        return Move(fx, fy, z0), Move(fx, _clamp(fy - 0.02), z1)
    p = pattern % 4
    if p == 0:  # slow push-in towards subject
        return Move(0.5, 0.5, 1.02), Move(_clamp(0.5 + (fx - 0.5) * 0.6), fy, 1.16)
    if p == 1:  # pull-out from subject
        return Move(fx, fy, 1.28), Move(0.5, 0.5, 1.04)
    if p == 2:  # pan left -> right
        return Move(0.38, fy, 1.18), Move(0.62, fy, 1.22)
    return Move(0.62, fy, 1.22), Move(0.38, fy, 1.18)  # pan right -> left


def _split_points(
    start: float, end: float, words: list[WordTiming], max_len: float = MAX_SHOT_SECONDS
) -> list[float]:
    """Return cut times inside [start, end] so no shot is much longer than max_len."""
    n = int((end - start) // max_len)
    if n <= 0 or not words:
        return []
    cuts: list[float] = []
    for k in range(1, n + 1):
        target = start + (end - start) * k / (n + 1)
        best = min(words[1:] or words, key=lambda w: abs(w.start - target))
        if best.start - start > 1.2 and end - best.start > 1.2:
            cuts.append(best.start - 0.05)
    return sorted(set(cuts))


def plan_shots(
    project: Project,
    lines: list[LineTiming],
    words: list[WordTiming],
    images: dict[int, ImageInfo],
    total: float,
) -> list[Shot]:
    shots: list[Shot] = []
    seen: set[int] = set()
    pattern = 0
    prev_visual = -2
    for lt in lines:
        line = project.lines[lt.index]
        start = 0.0 if not shots else max(lt.start - 0.05, shots[-1].start + 0.2)
        if line.card:
            shots.append(
                Shot(
                    start,
                    0.0,
                    lt.index,
                    -1,
                    "title",
                    Move(0.5, 0.5, 1.0),
                    Move(0.5, 0.5, 1.0),
                    line.era,
                    "",
                    card_text=line.card,
                )
            )
            prev_visual = -1
            continue
        info = images.get(line.visual) or ImageInfo(1080, 1920)
        line_words = [w for w in words if w.line == lt.index]
        cuts = [start, *_split_points(start, lt.end, line_words)]
        for j, cut in enumerate(cuts):
            same = line.visual == prev_visual
            first_of_video = not shots
            detail = same or j > 0
            portrait = info.aspect < 1.0
            if portrait:
                mode = "bleed"
            elif first_of_video and info.height >= 700:
                mode = "bleed"
            else:
                mode = "card"
            a, b = _moves(info, pattern, detail and not first_of_video)
            if first_of_video and mode == "bleed" and not portrait:
                a = Move(info.focus_x, info.focus_y, 1.7)
                b = Move(_clamp(info.focus_x + 0.08), info.focus_y, 1.1)
            pattern += 1
            shots.append(
                Shot(
                    cut,
                    0.0,
                    lt.index,
                    line.visual,
                    mode,
                    a,
                    b,
                    line.era,
                    line.kicker,
                    new_visual=line.visual not in seen,
                )
            )
            seen.add(line.visual)
            prev_visual = line.visual
    # close shot end times
    fixed: list[Shot] = []
    for i, s in enumerate(shots):
        end = shots[i + 1].start if i + 1 < len(shots) else total
        fixed.append(
            Shot(
                s.start,
                end,
                s.line,
                s.visual,
                s.mode,
                s.a,
                s.b,
                s.era,
                s.kicker,
                s.card_text,
                s.new_visual,
            )
        )
    return fixed
