"""JSON film spec for the long-form renderer.

A film is a list of scenes. Scenes that ``say`` something last as long as their
narration (plus padding); the others last ``hold`` seconds. Example::

    {"title": "Vecihi", "scenes": [
      {"kind": "document", "typed": ["İzinsiz uçuş."], "stamp": "CEZA",
       "say": [{"voice": "makam", "text": "İzinsiz uçuş."}]},
      {"kind": "photo", "image": "img/k6.png", "move": "in", "focus": [0.5, 0.4],
       "label": "Vecihi K-VI, 1925", "say": [{"text": "On beş dakika havada kalıyor."}]},
      {"kind": "chapter", "number": "1", "title": "Uçağını yakan adam"}
    ]}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KINDS = ("photo", "split", "document", "chapter", "titlecard", "date", "black", "end")
MOVES = ("in", "out", "left", "right", "up", "down", "still")
GRADES = ("sepia", "bw", "color")
FITS = ("cover", "contain")
SFX = ("", "typewriter", "stamp", "door")


class SpecError(ValueError):
    pass


@dataclass(slots=True)
class Say:
    text: str  # what the TTS reads (numbers spelled out)
    voice: str = ""  # role name, "" = main narrator
    sub: str = ""  # closed-caption text; defaults to ``text``

    @property
    def caption(self) -> str:
        return self.sub or self.text


@dataclass(slots=True)
class Scene:
    kind: str
    say: list[Say] = field(default_factory=list)
    hold: float = 0.0  # minimum length in seconds
    pad: tuple[float, float] = (0.5, 0.8)  # silence before the first / after the last line
    image: str = ""
    image2: str = ""  # split: right picture
    move: str = "in"
    focus: tuple[float, float] = (0.5, 0.45)
    grade: str = "sepia"
    grade2: str = "color"
    fit: str = "cover"
    label: str = ""  # small source line, bottom left
    label2: str = ""
    number: str = ""  # chapter number
    title: str = ""  # chapter / title card / date text
    typed: list[str] = field(default_factory=list)  # document lines
    stamp: str = ""
    note: str = ""  # small note on documents ("karar özeti")
    lines: list[str] = field(default_factory=list)  # end credits
    sfx: str = ""
    music: bool = True  # music bed under this scene
    lift: bool = False  # brighter (major) music from this scene on
    transition: str = "cross"  # cross | black | cut (into this scene)


@dataclass(slots=True)
class Film:
    title: str
    scenes: list[Scene]
    root: Path
    width: int = 1920
    height: int = 1080
    fps: int = 30

    def path(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else self.root / p


def _pair(v: Any, default: tuple[float, float]) -> tuple[float, float]:
    if v is None:
        return default
    if not (isinstance(v, list | tuple) and len(v) == 2):
        raise SpecError(f"iki sayı bekleniyordu: {v!r}")
    return float(v[0]), float(v[1])


def _choice(v: Any, allowed: tuple[str, ...], what: str, where: str) -> str:
    s = str(v)
    if s not in allowed:
        raise SpecError(f"{where}: bilinmeyen {what} '{s}' ({', '.join(allowed)})")
    return s


def parse_scene(raw: dict[str, Any], index: int, root: Path) -> Scene:
    where = f"sahne {index + 1}"
    if not isinstance(raw, dict):
        raise SpecError(f"{where}: nesne olmalı")
    kind = _choice(raw.get("kind", ""), KINDS, "tür", where)
    say = []
    for s in raw.get("say", []):
        if isinstance(s, str):
            s = {"text": s}
        if not str(s.get("text", "")).strip():
            raise SpecError(f"{where}: boş anlatım satırı")
        say.append(Say(str(s["text"]).strip(), str(s.get("voice", "")), str(s.get("sub", ""))))
    sc = Scene(
        kind=kind,
        say=say,
        hold=float(raw.get("hold", 0.0)),
        pad=_pair(raw.get("pad"), (0.5, 0.8)),
        image=str(raw.get("image", "")),
        image2=str(raw.get("image2", "")),
        move=_choice(raw.get("move", "in"), MOVES, "hareket", where),
        focus=_pair(raw.get("focus"), (0.5, 0.45)),
        grade=_choice(raw.get("grade", "sepia"), GRADES, "renk", where),
        grade2=_choice(raw.get("grade2", "color"), GRADES, "renk", where),
        fit=_choice(raw.get("fit", "cover"), FITS, "yerleşim", where),
        label=str(raw.get("label", "")),
        label2=str(raw.get("label2", "")),
        number=str(raw.get("number", "")),
        title=str(raw.get("title", "")),
        typed=[str(x) for x in raw.get("typed", [])],
        stamp=str(raw.get("stamp", "")),
        note=str(raw.get("note", "")),
        lines=[str(x) for x in raw.get("lines", [])],
        sfx=_choice(raw.get("sfx", ""), SFX, "efekt", where),
        music=bool(raw.get("music", True)),
        lift=bool(raw.get("lift", False)),
        transition=_choice(
            raw.get("transition", "cross"), ("cross", "black", "cut"), "geçiş", where
        ),
    )
    if kind in ("photo", "split") and not sc.image:
        raise SpecError(f"{where}: 'image' gerekli")
    if kind == "split" and not sc.image2:
        raise SpecError(f"{where}: 'image2' gerekli")
    for rel in (sc.image, sc.image2):
        if rel and not (root / rel).is_file() and not Path(rel).is_file():
            raise SpecError(f"{where}: görsel bulunamadı: {rel}")
    if not say and sc.hold <= 0:
        raise SpecError(f"{where}: anlatım yoksa 'hold' (saniye) gerekli")
    return sc


def load_film(path: Path) -> Film:
    data = json.loads(path.read_text(encoding="utf-8"))
    root = path.parent
    scenes = [parse_scene(s, i, root) for i, s in enumerate(data.get("scenes", []))]
    if not scenes:
        raise SpecError("hiç sahne yok")
    return Film(
        title=str(data.get("title", "")),
        scenes=scenes,
        root=root,
        width=int(data.get("width", 1920)),
        height=int(data.get("height", 1080)),
        fps=int(data.get("fps", 30)),
    )
