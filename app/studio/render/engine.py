"""Frame renderer: smooth sub-pixel camera moves, card layout for landscape
archive photos, film grade, kickers, word-by-word captions and title cards.

Every frame is drawn in numpy/OpenCV and piped to one ffmpeg process per shot
(ffmpeg's zoompan rounds to whole pixels and jitters; warpAffine does not).
"""

from __future__ import annotations

import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.studio.models import Era
from app.studio.render.planner import ImageInfo, Shot
from app.studio.text import WordTiming, chunk_words, tr_upper

F32 = npt.NDArray[np.float32]
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_BOLD = str(FONT_DIR / "Poppins-Bold.ttf")
FONT_MEDIUM = str(FONT_DIR / "Poppins-Medium.ttf")
YELLOW = (255, 214, 64)
ACCENT_BGR = np.array([0.25, 0.84, 1.0], np.float32)

TINTS: dict[Era, F32] = {  # BGR multipliers
    Era.OLD: np.array([0.86, 0.97, 1.08], np.float32),
    Era.GOLD: np.array([0.72, 0.95, 1.15], np.float32),
    Era.MODERN: np.array([1.12, 1.0, 0.86], np.float32),
    Era.NEUTRAL: np.array([0.95, 1.0, 1.03], np.float32),
}


def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def load_image(path: Path, *, grayscale: bool) -> F32:
    raw = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if raw is None:
        pil = Image.open(path).convert("RGB")
        raw = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
    img: F32 = raw.astype(np.float32) / 255.0
    if grayscale:
        g = img.mean(axis=2, keepdims=True)
        img = np.repeat(g, 3, axis=2)
    return img


_CASCADE: Any = None


def _face_cascade() -> Any:
    global _CASCADE
    if _CASCADE is None:
        _CASCADE = False
        data_dir = getattr(getattr(cv2, "data", None), "haarcascades", "")
        xml = Path(data_dir) / "haarcascade_frontalface_default.xml"
        if data_dir and xml.is_file():
            clf = cv2.CascadeClassifier(str(xml))
            if not clf.empty():
                _CASCADE = clf
    return _CASCADE


def detect_focus(img: F32) -> tuple[float, float]:
    """Largest face (slightly above its centre); else centre-high default."""
    h, w = img.shape[:2]
    cascade = _face_cascade()
    if cascade is False:
        return 0.5, 0.45
    gray = (img.mean(axis=2) * 255).astype(np.uint8)
    side = max(24, w // 20)
    faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(side, side))
    if len(faces):
        x, y, fw, fh = max(faces, key=lambda f: int(f[2]) * int(f[3]))
        return (float(x + fw / 2) / w, float(y + fh * 0.45) / h)
    return 0.5, 0.45


@dataclass(slots=True)
class Visuals:
    images: dict[int, F32]
    info: dict[int, ImageInfo]


def prepare_visuals(
    paths: dict[int, Path], focus: dict[int, tuple[float | None, float | None]]
) -> Visuals:
    images: dict[int, F32] = {}
    info: dict[int, ImageInfo] = {}
    for idx, p in paths.items():
        img = load_image(p, grayscale=False)
        sat = float(np.mean(np.std(img, axis=2)))
        if sat < 0.06:  # treat near-monochrome archive photos as true B&W
            img = np.repeat(img.mean(axis=2, keepdims=True), 3, axis=2)
        else:  # mute colours so archive + colour photos sit together
            g = img.mean(axis=2, keepdims=True)
            img = (g * 0.55 + img * 0.45).astype(np.float32)
        fx, fy = focus.get(idx, (None, None))
        if fx is None or fy is None:
            fx, fy = detect_focus(img)
        images[idx] = img
        info[idx] = ImageInfo(img.shape[1], img.shape[0], fx, fy)
    return Visuals(images, info)


class FrameRenderer:
    def __init__(
        self,
        shots: list[Shot],
        words: list[WordTiming],
        visuals: Visuals,
        *,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
    ) -> None:
        self.shots, self.vis = shots, visuals
        self.W, self.H, self.fps = width, height, fps
        self.s = width / 1080.0
        self.starts = [sh.start for sh in shots]
        self.chunks = chunk_words(words)
        self._font_cache: dict[tuple[int, str], Any] = {}
        self._cap_cache: dict[tuple[int, int], F32] = {}
        self._kick_cache: dict[str, F32] = {}
        self._title_cache: dict[str, tuple[F32, F32]] = {}
        self._bg_cache: dict[int, F32] = {}
        W, H = width, height
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self._yy, self._xx = yy, xx
        r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H * 0.47) / (H * 0.55)) ** 2)
        self.vignette: F32 = np.clip(1 - 0.75 * np.clip(r - 0.45, 0, 1) ** 1.6, 0, 1)[..., None]
        rng = np.random.default_rng(3)
        self.grain: list[F32] = []
        for _ in range(6):
            g = rng.standard_normal((H // 2, W // 2)).astype(np.float32)
            g = cv2.GaussianBlur(g, (0, 0), 0.7)
            self.grain.append(cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR)[..., None])

    # ------------------------------------------------------------ helpers
    def font(self, size: int, path: str = FONT_BOLD) -> Any:
        key = (size, path)
        if key not in self._font_cache:
            self._font_cache[key] = ImageFont.truetype(path, size)
        return self._font_cache[key]

    def crop_view(self, k: int, cx: float, cy: float, z: float, ww: int, wh: int) -> F32:
        src = self.vis.images[k]
        h, w = src.shape[:2]
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
        out: F32 = cv2.warpAffine(
            src, m, (ww, wh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT
        )
        if sc > 1.6:  # unsharp mask against upscale softness
            bl = cv2.GaussianBlur(out, (0, 0), 1.6 * self.s)
            out = np.clip(out * 1.45 - bl * 0.45, 0, 1)
        return out

    def card_bg(self, k: int) -> F32:
        if k not in self._bg_cache:
            b = self.crop_view(k, 0.5, 0.5, 1.0, max(self.W // 4, 8), max(self.H // 4, 8))
            b = cv2.GaussianBlur(b, (0, 0), 9)
            self._bg_cache[k] = (cv2.resize(b, (self.W, self.H)) * 0.32).astype(np.float32)
        return self._bg_cache[k]

    def over(
        self,
        dst: F32,
        rgba: F32,
        x: float,
        y: float,
        scale: float = 1.0,
        alpha: float = 1.0,
        color_rgb: tuple[float, float, float] | None = None,
    ) -> None:
        if scale != 1.0:
            rgba = cv2.resize(rgba, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        h, w = rgba.shape[:2]
        xi, yi = int(round(x)), int(round(y))
        x0, y0 = max(xi, 0), max(yi, 0)
        x1, y1 = min(xi + w, self.W), min(yi + h, self.H)
        if x1 <= x0 or y1 <= y0:
            return
        s = rgba[y0 - yi : y1 - yi, x0 - xi : x1 - xi]
        a = s[..., 3:4] * alpha
        if color_rgb is None:
            rgb = s[..., [2, 1, 0]]
        else:
            rgb = np.array(color_rgb[::-1], np.float32)
        dst[y0:y1, x0:x1] = dst[y0:y1, x0:x1] * (1 - a) + rgb * a

    def _rgba(self, img: Image.Image) -> F32:
        return np.asarray(img).astype(np.float32) / 255.0

    def caption(self, ci: int, active: int) -> F32:
        key = (ci, active)
        if key in self._cap_cache:
            return self._cap_cache[key]
        s = self.s
        f = self.font(int(84 * s))
        words = [tr_upper(w.word) for w in self.chunks[ci]]
        space = int(26 * s)
        widths = [f.getbbox(w)[2] - f.getbbox(w)[0] for w in words]
        lines = [list(range(len(words)))]
        if sum(widths) + space * (len(words) - 1) > 1010 * s and len(words) > 1:
            m = len(words) // 2 if len(words) > 2 else 1
            lines = [list(range(m)), list(range(m, len(words)))]
        pad, lh = int(40 * s), int(104 * s)
        img = Image.new("RGBA", (self.W, lh * len(lines) + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for li, line in enumerate(lines):
            lw = sum(widths[i] for i in line) + space * (len(line) - 1)
            x = (self.W - lw) / 2
            y = pad + li * lh
            for i in line:
                col = YELLOW if i == active else (255, 255, 255)
                d.text(
                    (x, y),
                    words[i],
                    font=f,
                    fill=(*col, 255),
                    stroke_width=max(int(9 * s), 1),
                    stroke_fill=(0, 0, 0, 255),
                )
                x += widths[i] + space
        out = self._with_shadow(img, int(10 * s), int(8 * s))
        self._cap_cache[key] = out
        return out

    def _with_shadow(self, img: Image.Image, blur: int, dy: int) -> F32:
        alpha = img.split()[3].filter(ImageFilter.GaussianBlur(max(blur, 1)))
        shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        shadow.putalpha(alpha.point(lambda v: int(v * 0.55)))
        base = Image.new("RGBA", img.size, (0, 0, 0, 0))
        base.alpha_composite(shadow, (0, dy))
        base.alpha_composite(img)
        return self._rgba(base)

    def kicker(self, text: str) -> F32:
        if text in self._kick_cache:
            return self._kick_cache[text]
        s = self.s
        f = self.font(int(40 * s))
        bb = f.getbbox(text)
        tw = bb[2] - bb[0]
        pad = int(32 * s)
        img = Image.new("RGBA", (tw + 2 * pad, int(84 * s)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            (0, int(8 * s), tw + 2 * pad - 1, int(76 * s)),
            radius=int(14 * s),
            fill=(12, 12, 12, 200),
        )
        d.rectangle((0, int(8 * s), int(8 * s), int(76 * s)), fill=(*YELLOW, 255))
        d.text((int(36 * s), int(14 * s)), text, font=f, fill=(255, 255, 255, 255))
        out = self._rgba(img)
        self._kick_cache[text] = out
        return out

    def title_art(self, text: str) -> tuple[F32, F32]:
        if text in self._title_cache:
            return self._title_cache[text]
        t = tr_upper(text)
        size = int(980 * self.s) if len(t) <= 2 else int(420 * self.s)
        f = self.font(size)
        while f.getbbox(t)[2] - f.getbbox(t)[0] > self.W * 0.88 and size > 40:
            size = int(size * 0.92)
            f = self.font(size)
        bb = f.getbbox(t)
        h = bb[3] - bb[1] + int(160 * self.s)
        img = Image.new("RGBA", (self.W, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text(
            ((self.W - (bb[2] - bb[0])) / 2 - bb[0], int(80 * self.s) - bb[1]),
            t,
            font=f,
            fill=(235, 255, 238, 255),
        )
        art = self._rgba(img)
        glow: F32 = cv2.GaussianBlur(art, (0, 0), 38 * self.s)
        self._title_cache[text] = (art, glow)
        return art, glow

    # ------------------------------------------------------------ frame
    def shot_at(self, t: float) -> int:
        idx = 0
        for i, st in enumerate(self.starts):
            if st <= t + 1e-6:
                idx = i
        return idx

    def frame(self, t: float) -> F32:
        si = self.shot_at(t)
        sh = self.shots[si]
        lt = t - sh.start
        p = lt / max(sh.duration, 1e-3)
        fi = int(round(t * self.fps))
        W, H, s = self.W, self.H, self.s

        if sh.mode == "title":
            return self._title_frame(sh, lt, fi)

        e = ease(p)
        cx = sh.a.cx + (sh.b.cx - sh.a.cx) * e
        cy = sh.a.cy + (sh.b.cy - sh.a.cy) * e
        z = sh.a.zoom + (sh.b.zoom - sh.a.zoom) * e
        if si > 0:
            z *= 1 + 0.07 * max(0.0, 1 - lt / 0.22) ** 2  # cut punch-in
        tint = TINTS.get(sh.era, TINTS[Era.OLD])

        if sh.mode == "bleed":
            view = self.crop_view(sh.visual, cx, cy, z, W, H)
            out = np.clip((view - 0.5) * 1.15 + 0.5, 0, 1) * tint
        else:
            out = self.card_bg(sh.visual).copy()
            wh = int(960 * s)
            y0 = int(H * 0.39 - wh / 2)
            view = self.crop_view(sh.visual, cx, cy, z, W, wh)
            view = np.clip((view - 0.5) * 1.15 + 0.5, 0, 1) * tint
            shadow = np.zeros((H, W), np.float32)
            shadow[y0 + int(14 * s) : y0 + wh + int(14 * s), :] = 1
            shadow = cv2.GaussianBlur(shadow, (0, 0), 22 * s)[..., None]
            out = out * (1 - 0.6 * shadow)
            out[y0 : y0 + wh, :] = view
            bw = max(int(3 * s), 1)
            out[y0 : y0 + bw, :] = 0.85 * ACCENT_BGR
            out[y0 + wh - bw : y0 + wh, :] = 0.85 * ACCENT_BGR

        flick = 1 + 0.025 * math.sin(t * 31) * math.sin(t * 5.1)
        out = out * flick * self.vignette + self.grain[fi % 6] * 0.045
        if si > 0:
            fl = max(0.0, 1 - lt / 0.1) * 0.55
            out = out * (1 - fl) + fl
        else:
            out = out * min(1.0, 0.35 + lt / 0.25)

        if sh.kicker:
            prev_k = self.shots[si - 1].kicker if si > 0 else ""
            ka = 1.0 if prev_k == sh.kicker else min(lt / 0.2, 1.0)
            self.over(out, self.kicker(sh.kicker), 60 * s - 30 * s * (1 - ka), 300 * s, 1.0, ka)
        self._draw_caption(out, t)
        return np.asarray(np.clip(out, 0, 1), dtype=np.float32)

    def _title_frame(self, sh: Shot, lt: float, fi: int) -> F32:
        W, H, s = self.W, self.H, self.s
        out = np.zeros((H, W, 3), np.float32)
        col = (
            np.array([0.15, 0.55, 0.7], np.float32)  # gold (BGR)
            if sh.era is Era.GOLD
            else np.array([0.25, 0.5, 0.12], np.float32)  # green
        )
        glow_rgb = (1.0, 0.85, 0.4) if sh.era is Era.GOLD else (0.45, 1.0, 0.55)
        g = np.exp(-((self._xx - W / 2) ** 2 + (self._yy - H * 0.45) ** 2) / (2 * (360 * s) ** 2))
        out += g[..., None] * col * (1.0 - 0.3 * min(lt / 0.8, 1))
        sc = 1.0 + 0.55 * max(0.0, 1 - lt / 0.14) ** 2
        shake = 26 * s * math.exp(-lt * 9)
        dx, dy = shake * math.sin(lt * 90), shake * math.cos(lt * 77)
        art, glow = self.title_art(sh.card_text)
        ah, aw = art.shape[:2]
        x, y = (W - aw * sc) / 2 + dx, H * 0.45 - ah * sc / 2 + dy
        self.over(out, glow, x, y, sc, 1.0, glow_rgb)
        self.over(out, glow, x, y, sc, 0.8, glow_rgb)
        self.over(out, art, x, y, sc)
        flash = max(0.0, 1 - lt / 0.12)
        out = out * (1 - flash) + flash
        out += self.grain[fi % 6] * 0.035
        return np.asarray(np.clip(out, 0, 1), dtype=np.float32)

    def _draw_caption(self, out: F32, t: float) -> None:
        for ci, ch in enumerate(self.chunks):
            cs = ch[0].start - 0.05
            nxt = self.chunks[ci + 1] if ci + 1 < len(self.chunks) else None
            ce = nxt[0].start - 0.05 if nxt and nxt[0].line == ch[0].line else ch[-1].end + 0.12
            if cs <= t < ce:
                act = max([j for j, w in enumerate(ch) if w.start <= t + 0.03] or [0])
                cap = self.caption(ci, act)
                pop = 1 + 0.10 * max(0.0, 1 - (t - cs) / 0.12)
                h, w = cap.shape[:2]
                self.over(out, cap, (self.W - w * pop) / 2, 1345 * self.s - h * pop / 2, pop)
                return


def to_bgr8(frame: F32) -> npt.NDArray[np.uint8]:
    return (frame * 255 + 0.5).astype(np.uint8)


def encode_shot(renderer: FrameRenderer, index: int, path: Path, total: float) -> int:
    """Render one shot to its own mp4 (written atomically)."""
    sh = renderer.shots[index]
    fps = renderer.fps
    f0 = int(round(sh.start * fps))
    f1 = int(round(min(sh.end, total) * fps))
    tmp = path.with_name(path.stem + ".part.mp4")
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
            f"{renderer.W}x{renderer.H}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            str(tmp),
        ],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin is not None
    for fi in range(f0, f1):
        proc.stdin.write(to_bgr8(renderer.frame(fi / fps)).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for shot {index}")
    os.replace(tmp, path)
    return f1 - f0
