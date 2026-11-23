"""Frame drawing for the long-form renderer.

Design rules (see docs/longform/vecihi-hurkus/senaryo.md): real pictures only, one
slow camera move per picture, quiet serif typography, archive in sepia/black and
white, colour reserved for the present day, no burned-in captions, no flashes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw, ImageFont

from app.longform.spec import Film, Scene
from app.longform.timeline import Timeline
from app.studio.text import tr_upper

F32 = npt.NDArray[np.float32]

_FONT_DIRS = (Path("/usr/share/fonts/truetype/freefont"), Path("/usr/share/fonts/truetype/dejavu"))
_BUNDLED = Path(__file__).resolve().parent.parent / "studio" / "assets" / "fonts"


def _font_path(*names: str) -> str:
    for d in _FONT_DIRS:
        for n in names:
            if (d / n).is_file():
                return str(d / n)
    return str(_BUNDLED / "Poppins-Medium.ttf")


SERIF = _font_path("FreeSerif.ttf", "DejaVuSerif.ttf")
SERIF_BOLD = _font_path("FreeSerifBold.ttf", "DejaVuSerif-Bold.ttf")
SERIF_ITALIC = _font_path("FreeSerifItalic.ttf", "DejaVuSerif.ttf")
MONO = _font_path("FreeMono.ttf", "DejaVuSansMono.ttf")
SANS = _font_path("FreeSans.ttf", "DejaVuSans.ttf")

XFADE = 0.8  # cross-dissolve length between pictures
BLACK_FADE = 0.6  # fade to/from black around cards
SEPIA = np.array([0.78, 0.90, 1.0], np.float32)  # BGR multipliers
STAMP_RED = (40, 40, 178)  # BGR 0-255


def smooth(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def load_image(path: Path) -> F32:
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"görsel okunamadı: {path}")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        a = img[..., 3:4].astype(np.float32) / 255
        img = (img[..., :3].astype(np.float32) * a + 255 * (1 - a)).astype(np.uint8)
    out: F32 = img.astype(np.float32)
    out *= np.float32(1 / 255.0)
    return out


def grade(img: F32, kind: str) -> F32:
    """Archive pictures: stretched contrast + sepia / neutral; colour stays colour."""
    if kind == "color":
        out = np.clip((img - 0.5) * 1.05 + 0.5, 0, 1)
        return np.asarray(out, dtype=np.float32)
    g = img[..., 0] * 0.114 + img[..., 1] * 0.587 + img[..., 2] * 0.299
    lo, hi = np.percentile(g, (1.0, 99.0))
    g = np.clip((g - lo) / max(hi - lo, 1e-3), 0, 1) * 0.90 + 0.04
    tint = SEPIA if kind == "sepia" else np.array([0.97, 0.99, 1.0], np.float32)
    return np.asarray(g[..., None] * tint, dtype=np.float32)


def text_rgba(
    text: str,
    font_path: str,
    size: int,
    color: tuple[int, int, int] = (235, 228, 214),
    spacing: float = 0.0,
) -> F32:
    """Text as a float RGBA array (RGB order), with optional letter spacing."""
    f = ImageFont.truetype(font_path, size)
    if spacing:
        widths = [f.getlength(ch) for ch in text]
        w = int(sum(widths) + spacing * size * max(len(text) - 1, 0)) + 4
    else:
        w = int(f.getlength(text)) + 4
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (max(w, 1), asc + desc + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if spacing:
        x = 2.0
        for ch, cw in zip(text, widths, strict=True):
            d.text((x, 2), ch, font=f, fill=(*color, 255))
            x += cw + spacing * size
    else:
        d.text((2, 2), text, font=f, fill=(*color, 255))
    return np.asarray(img).astype(np.float32) / 255.0


def over(dst: F32, rgba: F32, x: float, y: float, alpha: float = 1.0) -> None:
    """Alpha-composite an RGB(A) overlay onto a BGR frame in place."""
    if alpha <= 0:
        return
    h, w = rgba.shape[:2]
    H, W = dst.shape[:2]
    xi, yi = int(round(x)), int(round(y))
    x0, y0, x1, y1 = max(xi, 0), max(yi, 0), min(xi + w, W), min(yi + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    s = rgba[y0 - yi : y1 - yi, x0 - xi : x1 - xi]
    a = s[..., 3:4] * alpha
    dst[y0:y1, x0:x1] = dst[y0:y1, x0:x1] * (1 - a) + s[..., [2, 1, 0]] * a


@dataclass(slots=True)
class Plate:
    """A prepared picture: either a large graded image (cover) or a composed canvas."""

    img: F32
    cover: bool


class FilmFrames:
    def __init__(self, film: Film, timeline: Timeline) -> None:
        self.film, self.tl = film, timeline
        self.W, self.H = film.width, film.height
        self.s = film.width / 1920.0
        self._plates: dict[tuple[int, int], Plate] = {}
        self._text: dict[tuple[Any, ...], F32] = {}
        W, H = self.W, self.H
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W * 0.6)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2)
        self.vignette: F32 = np.clip(1 - 0.55 * np.clip(r - 0.55, 0, 1) ** 1.8, 0, 1)[..., None]
        rng = np.random.default_rng(11)
        self.grain: list[F32] = []
        for _ in range(8):
            g = rng.standard_normal((H // 2, W // 2)).astype(np.float32)
            g = cv2.GaussianBlur(g, (0, 0), 0.6)
            self.grain.append(cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR)[..., None])
        self._paper: F32 | None = None
        self._desk: F32 | None = None

    # ------------------------------------------------------------ cached pieces
    def txt(self, text: str, font: str, size: float, **kw: Any) -> F32:
        key = (text, font, int(size * self.s), tuple(sorted(kw.items())))
        if key not in self._text:
            self._text[key] = text_rgba(text, font, int(size * self.s), **kw)
        return self._text[key]

    def desk(self) -> F32:
        """Dark warm background behind framed pictures and documents."""
        if self._desk is None:
            rng = np.random.default_rng(5)
            n = rng.standard_normal((self.H // 16, self.W // 16)).astype(np.float32)
            n = cv2.resize(cv2.GaussianBlur(n, (0, 0), 2.5), (self.W, self.H))[..., None]
            base = np.array([0.055, 0.065, 0.075], np.float32)
            self._desk = np.asarray((base + 0.012 * n) * self.vignette, dtype=np.float32)
        return self._desk

    def plate(self, si: int, which: int = 0) -> Plate:
        key = (si, which)
        if key in self._plates:
            return self._plates[key]
        sc = self.film.scenes[si]
        rel = sc.image if which == 0 else sc.image2
        g = grade(load_image(self.film.path(rel)), sc.grade if which == 0 else sc.grade2)
        if sc.kind == "photo" and sc.fit == "cover":
            h, w = g.shape[:2]
            lim = 2.4 * max(self.W / w, self.H / h)
            if lim < 1:  # keep enough pixels for a 1.15x push, drop the rest
                g = cv2.resize(g, (int(w * lim), int(h * lim)), interpolation=cv2.INTER_AREA)
            plate = Plate(g, True)
        elif sc.kind == "split":
            plate = Plate(self._framed(g, self.W * 0.44, self.H * 0.62, on_desk=False), False)
        else:
            plate = Plate(self._framed(g, self.W * 0.86, self.H * 0.84), False)
        self._plates[key] = plate
        return plate

    def _framed(self, img: F32, max_w: float, max_h: float, *, on_desk: bool = True) -> F32:
        """A print on the desk: scaled to fit, thin light border and a soft shadow."""
        h, w = img.shape[:2]
        k = min(max_w / w, max_h / h)
        pw, ph = max(int(w * k), 2), max(int(h * k), 2)
        pic = cv2.resize(img, (pw, ph), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
        b = max(int(6 * self.s), 2)
        pic = cv2.copyMakeBorder(pic, b, b, b, b, cv2.BORDER_CONSTANT, value=(0.86, 0.9, 0.92))
        if not on_desk:
            return np.asarray(pic, dtype=np.float32)
        canvas = self.desk().copy()
        ph, pw = pic.shape[:2]
        x0, y0 = (self.W - pw) // 2, (self.H - ph) // 2
        shadow = np.zeros((self.H, self.W), np.float32)
        off = int(14 * self.s)
        shadow[y0 + off : y0 + ph + off, x0 + off // 2 : x0 + pw + off // 2] = 1
        shadow = cv2.GaussianBlur(shadow, (0, 0), 24 * self.s)[..., None]
        canvas = canvas * (1 - 0.7 * shadow)
        canvas[y0 : y0 + ph, x0 : x0 + pw] = pic
        return np.asarray(canvas, dtype=np.float32)

    def paper(self) -> F32:
        """A sheet of aged typing paper, filling the frame (the camera sits close)."""
        if self._paper is None:
            rng = np.random.default_rng(9)
            W, H = self.W, self.H
            low = rng.standard_normal((H // 40, W // 40)).astype(np.float32)
            low = cv2.resize(cv2.GaussianBlur(low, (0, 0), 1.5), (W, H))
            fine = rng.standard_normal((H, W)).astype(np.float32)
            fine = cv2.GaussianBlur(fine, (0, 0), 0.8)
            base = np.array([0.74, 0.84, 0.89], np.float32)  # cream, BGR
            p = base + (0.035 * low + 0.018 * fine)[..., None]
            self._paper = np.asarray(np.clip(p * self.vignette, 0, 1), dtype=np.float32)
        return self._paper

    # ------------------------------------------------------------ camera
    def _move(self, sc: Scene, p: float) -> tuple[float, float, float]:
        """(cx, cy, zoom) for progress ``p`` in [0, 1] of the scene."""
        fx, fy = sc.focus
        e = smooth(p)
        if sc.move == "in":
            return 0.5 + (fx - 0.5) * e, 0.5 + (fy - 0.5) * e, 1.0 + 0.12 * e
        if sc.move == "out":
            return fx + (0.5 - fx) * e, fy + (0.5 - fy) * e, 1.12 - 0.12 * e
        if sc.move in ("left", "right"):
            a, b = (0.62, 0.38) if sc.move == "left" else (0.38, 0.62)
            return a + (b - a) * e, fy, 1.15
        if sc.move in ("up", "down"):
            a, b = (0.62, 0.38) if sc.move == "up" else (0.38, 0.62)
            return fx, a + (b - a) * e, 1.15
        return fx, fy, 1.04

    def view(self, img: F32, cx: float, cy: float, z: float, ww: int, wh: int) -> F32:
        h, w = img.shape[:2]
        a = ww / wh
        if w / h > a:
            ch = h / z
            cw = ch * a
        else:
            cw = w / z
            ch = cw / a
        x0 = float(np.clip(cx * w - cw / 2, 0, w - cw))
        y0 = float(np.clip(cy * h - ch / 2, 0, h - ch))
        sc = ww / cw
        m = np.array([[sc, 0, -x0 * sc], [0, sc, -y0 * sc]], np.float32)
        flags = cv2.INTER_AREA if sc < 1 else cv2.INTER_CUBIC
        out = cv2.warpAffine(img, m, (ww, wh), flags=flags, borderMode=cv2.BORDER_REFLECT)
        return np.asarray(out, dtype=np.float32)

    # ------------------------------------------------------------ scenes
    def scene_frame(self, si: int, lt: float) -> F32:
        sc = self.film.scenes[si]
        dur = self.tl.scenes[si].duration
        p = lt / max(dur, 1e-3)
        fn = getattr(self, f"_{sc.kind}")
        out: F32 = fn(si, sc, lt, p, dur)
        return out

    def _photo(self, si: int, sc: Scene, lt: float, p: float, dur: float) -> F32:
        pl = self.plate(si)
        cx, cy, z = self._move(sc, p)
        if not pl.cover:  # framed print: gentle push only, never show past the canvas
            z = 1.0 + (z - 1.0) * 0.45
        out = self.view(pl.img, cx, cy, z, self.W, self.H)
        out = out * self.vignette if pl.cover else out
        self._label(out, sc.label, lt, dur)
        return np.asarray(out, dtype=np.float32)

    def _split(self, si: int, sc: Scene, lt: float, p: float, dur: float) -> F32:
        out = self.desk().copy()
        left, right = self.plate(si, 0).img, self.plate(si, 1).img
        cy = self.H * 0.44
        xl = self.W * 0.27 - left.shape[1] / 2
        xr = self.W * 0.73 - right.shape[1] / 2
        rgba_l = np.dstack([left[..., ::-1], np.ones(left.shape[:2], np.float32)])
        rgba_r = np.dstack([right[..., ::-1], np.ones(right.shape[:2], np.float32)])
        over(out, rgba_l, xl, cy - left.shape[0] / 2)
        a2 = smooth((lt - 1.2) / 1.0)  # the present day arrives after a beat
        over(out, rgba_r, xr, cy - right.shape[0] / 2, a2)
        for text, x, a in ((sc.label, self.W * 0.27, 1.0), (sc.label2, self.W * 0.73, a2)):
            if text:
                t = self.txt(text, SERIF, 44, spacing=0.12)
                over(out, t, x - t.shape[1] / 2, self.H * 0.84, a)
        return out

    def _document(self, si: int, sc: Scene, lt: float, p: float, dur: float) -> F32:
        out = self.paper().copy()
        t0, t1 = typing_window(self.film, self.tl, si)
        start = self.tl.scenes[si].start
        total = sum(len(x) for x in sc.typed) or 1
        shown = int(total * smooth((start + lt - t0) / max(t1 - t0, 1e-3)) + 0.5)
        size = 50
        lh = int(size * 1.55 * self.s)
        y = self.H * 0.5 - lh * len(sc.typed) / 2 - (lh if sc.stamp else 0) * 0.6
        x = self.W * 0.17
        left = shown
        for line in sc.typed:
            part = line[: max(left, 0)]
            left -= len(line)
            if part:
                t = self.txt(part, MONO, size, color=(28, 26, 24))
                over(out, t, x, y, 0.92)
            y += lh
        if sc.stamp:
            ts = t1 + 0.35 - start
            if lt >= ts:
                k = smooth((lt - ts) / 0.14)
                stamp = self._stamp(sc.stamp)
                scale = 1.35 - 0.35 * k
                st = cv2.resize(stamp, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
                over(out, st, self.W * 0.62 - st.shape[1] / 2, y + lh * 0.2, 0.9 * k)
        if sc.note:
            n = self.txt(sc.note, SERIF_ITALIC, 30, color=(90, 84, 76))
            over(out, n, self.W * 0.83 - n.shape[1], self.H * 0.9, 0.9)
        # the camera drifts slowly across the sheet
        z = 1.0 + 0.035 * smooth(p)
        return self.view(out, 0.5, 0.5, z, self.W, self.H)

    def _stamp(self, text: str) -> F32:
        key = ("stamp", text)
        if key in self._text:
            return self._text[key]
        size = int(74 * self.s)
        f = ImageFont.truetype(SERIF_BOLD, size)
        tw = int(f.getlength(tr_upper(text)))
        pad = int(30 * self.s)
        w, h = tw + 2 * pad, size + 2 * pad
        img = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r, g, b = STAMP_RED[::-1]
        bw = max(int(7 * self.s), 2)
        d.rectangle((20, 20, 20 + w, 20 + h), outline=(r, g, b, 255), width=bw)
        d.text((20 + pad, 20 + pad - size * 0.12), tr_upper(text), font=f, fill=(r, g, b, 255))
        img = img.rotate(-7, resample=Image.Resampling.BICUBIC, expand=True)
        arr = np.asarray(img).astype(np.float32) / 255.0
        rng = np.random.default_rng(4)  # worn ink: uneven pressure, a few gaps
        n = cv2.GaussianBlur(rng.random(arr.shape[:2]).astype(np.float32), (0, 0), 1.2)
        arr[..., 3] *= np.clip((n - 0.32) * 3.0, 0.15, 1.0)
        self._text[key] = arr
        return arr

    def _chapter(self, si: int, sc: Scene, lt: float, p: float, dur: float) -> F32:
        out = np.zeros((self.H, self.W, 3), np.float32)
        a = self._card_alpha(lt, dur)
        num = self.txt(f"BÖLÜM {sc.number}", SANS, 30, color=(170, 160, 145), spacing=0.45)
        title = self.txt(tr_upper(sc.title), SERIF, 84, color=(236, 230, 218), spacing=0.06)
        over(out, num, (self.W - num.shape[1]) / 2, self.H * 0.40, a)
        lw = int(110 * self.s)
        y = int(self.H * 0.40 + num.shape[0] + 22 * self.s)
        out[y : y + max(int(2 * self.s), 1), (self.W - lw) // 2 : (self.W + lw) // 2] = 0.55 * a
        over(out, title, (self.W - title.shape[1]) / 2, y + 30 * self.s, a)
        return out

    def _titlecard(self, si: int, sc: Scene, lt: float, p: float, dur: float) -> F32:
        out = np.zeros((self.H, self.W, 3), np.float32)
        t = self.txt(tr_upper(sc.title), SERIF, 150, color=(238, 232, 220), spacing=0.32)
        over(
            out, t, (self.W - t.shape[1]) / 2, (self.H - t.shape[0]) / 2, self._card_alpha(lt, dur)
        )
        return out

    def _date(self, si: int, sc: Scene, lt: float, p: float, dur: float) -> F32:
        out = np.zeros((self.H, self.W, 3), np.float32)
        t = self.txt(sc.title, SERIF, 72, color=(225, 218, 205), spacing=0.08)
        over(
            out, t, (self.W - t.shape[1]) / 2, (self.H - t.shape[0]) / 2, self._card_alpha(lt, dur)
        )
        return out

    def _black(self, si: int, sc: Scene, lt: float, p: float, dur: float) -> F32:
        return np.zeros((self.H, self.W, 3), np.float32)

    def _end(self, si: int, sc: Scene, lt: float, p: float, dur: float) -> F32:
        out = np.zeros((self.H, self.W, 3), np.float32)
        a = self._card_alpha(lt, dur)
        head = self.txt(sc.title or "Kaynaklar", SERIF, 48, color=(230, 224, 212), spacing=0.1)
        over(out, head, (self.W - head.shape[1]) / 2, self.H * 0.1, a)
        n = max(len(sc.lines), 1)
        size = min(26.0, 760 / n / 1.5)
        y = self.H * 0.1 + head.shape[0] + 40 * self.s
        for line in sc.lines:
            t = self.txt(line, SANS, size, color=(175, 168, 156))
            over(out, t, (self.W - t.shape[1]) / 2, y, a)
            y += size * 1.5 * self.s
        return out

    def _card_alpha(self, lt: float, dur: float) -> float:
        return smooth(lt / 0.9) * smooth((dur - lt) / 0.7)

    def _label(self, out: F32, text: str, lt: float, dur: float) -> None:
        if not text:
            return
        a = smooth((lt - 0.8) / 0.8) * smooth((dur - 0.6 - lt) / 0.6)
        t = self.txt(text, SERIF_ITALIC, 30, color=(228, 222, 210))
        sh = self.txt(text, SERIF_ITALIC, 30, color=(0, 0, 0))
        x, y = 64 * self.s, self.H - 64 * self.s - t.shape[0]
        over(out, sh, x + 2 * self.s, y + 2 * self.s, 0.6 * a)
        over(out, t, x, y, 0.9 * a)

    # ------------------------------------------------------------ whole frame
    def scene_at(self, t: float) -> int:
        for i, slot in enumerate(self.tl.scenes):
            if t < slot.end:
                return i
        return len(self.tl.scenes) - 1

    def frame(self, t: float, fi: int) -> F32:
        si = self.scene_at(t)
        slot = self.tl.scenes[si]
        lt = t - slot.start
        out = self.scene_frame(si, lt)
        sc = self.film.scenes[si]
        nxt = si + 1 if si + 1 < len(self.film.scenes) else None
        cards = ("chapter", "titlecard", "date", "black", "end")
        if nxt is not None:
            ns = self.film.scenes[nxt]
            left = slot.end - t
            if ns.transition == "cross" and sc.kind not in cards and ns.kind not in cards:
                if left < XFADE:
                    k = smooth(1 - left / XFADE)
                    out = out * (1 - k) + self.scene_frame(nxt, 0.0) * k
            elif ns.transition != "cut" and sc.kind not in cards and left < BLACK_FADE:
                out = out * smooth(left / BLACK_FADE)
        prev = self.film.scenes[si - 1] if si > 0 else None
        if sc.kind not in cards and (
            prev is None or prev.kind in cards or sc.transition == "black"
        ):
            if lt < BLACK_FADE:
                out = out * smooth(lt / BLACK_FADE)
        amount = 0.014 if sc.grade != "color" or sc.kind in ("document",) else 0.006
        if sc.kind not in ("black",):
            out = out + self.grain[fi % len(self.grain)] * amount
        flicker = 1.0 + (0.008 * math.sin(t * 23.0) if sc.grade != "color" else 0.0)
        return np.asarray(np.clip(out * flicker, 0, 1), dtype=np.float32)


def typing_window(film: Film, tl: Timeline, si: int) -> tuple[float, float]:
    """When the document's text is typed: across the scene's narration (or its hold)."""
    own = [ln for ln in tl.lines if ln.scene == si]
    slot = tl.scenes[si]
    if own:
        return own[0].start, max(own[-1].end - 0.2, own[0].start + 0.5)
    return slot.start + 0.4, slot.start + max(slot.duration * 0.7, 0.8)
