from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


@dataclass(frozen=True, slots=True)
class VisualBeautificationResult:
    """Result of deterministic image enhancement with safe original fallback."""

    original_path: Path
    output_path: Path
    width: int
    height: int
    changed: bool
    operations: tuple[str, ...]
    fallback_reason: str | None = None


class VisualBeautifier:
    """Applies deterministic, portrait-safe image improvements without AI."""

    def __init__(
        self,
        *,
        target_width: int = 1080,
        target_height: int = 1920,
        sharpness: float = 1.08,
        contrast: float = 1.04,
    ) -> None:
        if target_width <= 0 or target_height <= 0:
            raise ValueError("Target dimensions must be positive")
        if sharpness <= 0 or contrast <= 0:
            raise ValueError("Enhancement factors must be positive")

        self._target_width = target_width
        self._target_height = target_height
        self._sharpness = sharpness
        self._contrast = contrast

    def beautify(
        self,
        source_path: Path,
        output_path: Path,
    ) -> VisualBeautificationResult:
        """Beautify an image, returning the original path if processing fails."""

        try:
            return self._process(source_path, output_path)
        except Exception as exc:
            return self._fallback(source_path, str(exc))

    def _process(
        self,
        source_path: Path,
        output_path: Path,
    ) -> VisualBeautificationResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(source_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image = ImageOps.fit(
                image,
                (self._target_width, self._target_height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            image = ImageEnhance.Contrast(image).enhance(self._contrast)
            image = ImageEnhance.Sharpness(image).enhance(self._sharpness)
            image.save(output_path, format="JPEG", quality=92, optimize=True)

        return VisualBeautificationResult(
            original_path=source_path,
            output_path=output_path,
            width=self._target_width,
            height=self._target_height,
            changed=True,
            operations=(
                "exif_orientation",
                "portrait_center_crop",
                "portrait_resize",
                "light_contrast",
                "light_sharpen",
            ),
        )

    @staticmethod
    def _fallback(source_path: Path, reason: str) -> VisualBeautificationResult:
        with Image.open(source_path) as image:
            width, height = image.size

        return VisualBeautificationResult(
            original_path=source_path,
            output_path=source_path,
            width=width,
            height=height,
            changed=False,
            operations=(),
            fallback_reason=reason,
        )
