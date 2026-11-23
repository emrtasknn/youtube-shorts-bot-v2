"""YouTube thumbnail for a long-form film: a real portrait, two lines, one stamp."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.longform.frames import SERIF_BOLD, grade, load_image, over, text_rgba
from app.studio.text import tr_upper

W, H = 1280, 720


def _stamp(text: str, size: int) -> np.ndarray:
    f = ImageFont.truetype(SERIF_BOLD, size)
    t = tr_upper(text)
    tw = int(f.getlength(t))
    pad = size // 3
    w, h = tw + 2 * pad, int(size * 1.25) + 2 * pad
    img = Image.new("RGBA", (w + 30, h + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((15, 15, 15 + w, 15 + h), outline=(200, 32, 32, 255), width=max(size // 9, 3))
    d.text((15 + pad, 15 + pad), t, font=f, fill=(200, 32, 32, 255))
    img = img.rotate(-8, resample=Image.Resampling.BICUBIC, expand=True)
    arr = np.asarray(img).astype(np.float32) / 255.0
    rng = np.random.default_rng(4)
    n = cv2.GaussianBlur(rng.random(arr.shape[:2]).astype(np.float32), (0, 0), 1.0)
    arr[..., 3] *= np.clip((n - 0.25) * 3.0, 0.35, 1.0)
    return arr


def make_thumbnail(portrait: Path, lines: list[str], stamp: str, dest: Path) -> Path:
    out = np.zeros((H, W, 3), np.float32)
    out[:] = (0.05, 0.06, 0.07)
    pic = grade(load_image(portrait), "sepia")
    ph = H
    pw = int(pic.shape[1] * ph / pic.shape[0])
    pic = cv2.resize(pic, (pw, ph), interpolation=cv2.INTER_CUBIC)
    pic = np.clip((pic - 0.5) * 1.25 + 0.52, 0, 1)
    x0 = 0
    fade = np.clip((np.arange(pw) - (pw - 120)) / 120.0, 0, 1)[None, :, None]
    region = out[:, x0 : x0 + pw]
    out[:, x0 : x0 + pw] = (
        pic[:, : region.shape[1]] * (1 - fade[:, : region.shape[1]])
        + region * fade[:, : region.shape[1]]
    )
    x = x0 + pw + 30
    y = 120.0
    for line in lines:
        t = text_rgba(tr_upper(line), SERIF_BOLD, 108, color=(245, 238, 224))
        over(out, t, x, y)
        y += t.shape[0] * 0.95
    st = _stamp(stamp, 62)
    over(out, st, x - 10, y + 20)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(
        str(dest), (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 92]
    )
    return dest
