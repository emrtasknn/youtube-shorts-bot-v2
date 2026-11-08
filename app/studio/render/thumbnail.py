"""Vertical (Shorts feed) and horizontal (search/desktop) thumbnails."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.studio.render.engine import FONT_BOLD, YELLOW, detect_focus, load_image
from app.studio.text import tr_upper


def _wrap(text: str, max_lines: int = 3) -> list[str]:
    words = tr_upper(text).split()
    if len(words) <= 2:
        return [" ".join(words)] if len(" ".join(words)) <= 12 else words
    per = -(-len(words) // min(max_lines, len(words)))
    lines = [" ".join(words[i : i + per]) for i in range(0, len(words), per)]
    return lines[:max_lines]


def _fit_font(lines: list[str], max_w: float, size: int) -> ImageFont.FreeTypeFont:
    while size > 30:
        f = ImageFont.truetype(FONT_BOLD, size)
        if all(f.getbbox(ln)[2] - f.getbbox(ln)[0] <= max_w for ln in lines):
            return f
        size -= 6
    return ImageFont.truetype(FONT_BOLD, size)


def make_thumbnail(
    image_path: Path,
    text: str,
    out: Path,
    *,
    width: int,
    height: int,
    label: str = "",
    focus: tuple[float, float] | None = None,
) -> Path:
    img = load_image(image_path, grayscale=False)
    h, w = img.shape[:2]
    fx, fy = focus or detect_focus(img)
    a = width / height
    if w / h > a:
        ch, cw = float(h), h * a
    else:
        cw, ch = float(w), w / a
    horizontal = width > height
    # horizontal: subject on the left third, text on the right
    tx = fx - (0.28 if horizontal else 0.0) * (cw / w)
    x0 = float(np.clip(tx * w - cw / 2, 0, w - cw))
    y0 = float(np.clip(fy * h - ch * 0.55, 0, h - ch))
    crop = img[int(y0) : int(y0 + ch), int(x0) : int(x0 + cw)]
    crop = cv2.resize(crop, (width, height), interpolation=cv2.INTER_CUBIC)
    crop = np.clip((crop - 0.5) * 1.25 + 0.5, 0, 1)
    rgb = (crop[..., ::-1] * 255).astype(np.uint8)
    base = Image.fromarray(rgb).convert("RGBA")

    # darkening gradient behind the text
    grad = Image.new("L", (width, height), 0)
    gd = ImageDraw.Draw(grad)
    if horizontal:
        for gx in range(width):
            gd.line([(gx, 0), (gx, height)], fill=int(220 * max(0.0, (gx / width - 0.35) / 0.65)))
    else:
        for gy in range(height):
            gd.line([(0, gy), (width, gy)], fill=int(230 * max(0.0, 1 - gy / (height * 0.55))))
    shade = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    shade.putalpha(grad)
    base.alpha_composite(shade)

    lines = _wrap(text)
    max_w = width * (0.52 if horizontal else 0.9)
    font = _fit_font(lines, max_w, int(height * (0.17 if horizontal else 0.1)))
    lh = int(font.size * 1.08)
    y = int(height * (0.5 - lh * len(lines) / (2 * height))) if horizontal else int(height * 0.12)
    text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(text_layer)
    stroke = max(int(font.size * 0.08), 4)
    for ln in lines:
        bb = font.getbbox(ln)
        tw = bb[2] - bb[0]
        x = (width * 0.96 - tw) if horizontal else (width - tw) / 2
        d.text(
            (x - bb[0], y),
            ln,
            font=font,
            fill=(*YELLOW, 255),
            stroke_width=stroke,
            stroke_fill=(0, 0, 0, 255),
        )
        y += lh
    if label:
        lf = ImageFont.truetype(FONT_BOLD, int(height * (0.06 if horizontal else 0.032)))
        lab = tr_upper(label)
        lb = lf.getbbox(lab)
        lw = lb[2] - lb[0]
        lx = (width * 0.96 - lw) if horizontal else (width - lw) / 2
        ly = int(height * 0.86)
        d.text(
            (lx - lb[0], ly),
            lab,
            font=lf,
            fill=(255, 255, 255, 255),
            stroke_width=5,
            stroke_fill=(0, 0, 0, 255),
        )
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow.putalpha(text_layer.split()[3].filter(ImageFilter.GaussianBlur(12)))
    base.alpha_composite(shadow, (0, 0))
    base.alpha_composite(text_layer)
    out.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(out, quality=93)
    return out
