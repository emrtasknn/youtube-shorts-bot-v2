from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DuckingConfig:
    background_volume: float = 0.18
    threshold: float = 0.03
    ratio: float = 8.0
    attack_ms: float = 20.0
    release_ms: float = 250.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.background_volume <= 1.0:
            raise ValueError("background_volume must be between 0 and 1")
        if not 0.0 < self.threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        if self.ratio < 1.0:
            raise ValueError("ratio must be >= 1")
        if self.attack_ms <= 0 or self.release_ms <= 0:
            raise ValueError("attack_ms and release_ms must be positive")


class AudioDucking:
    """Builds deterministic FFmpeg audio-ducking filters."""

    def __init__(self, config: DuckingConfig | None = None) -> None:
        self.config = config or DuckingConfig()

    def build_filter(
        self,
        *,
        voice_label: str = "voice",
        background_label: str = "background",
        output_label: str = "aout",
    ) -> str:
        config = self.config
        sidechain_label = f"{voice_label}_sidechain"
        return (
            f"[{background_label}]volume={config.background_volume:g}[bgm];"
            f"[{voice_label}]asplit=2[{voice_label}_mix][{sidechain_label}];"
            f"[bgm][{sidechain_label}]sidechaincompress="
            f"threshold={config.threshold:g}:"
            f"ratio={config.ratio:g}:"
            f"attack={config.attack_ms:g}:"
            f"release={config.release_ms:g}:"
            "makeup=1[ducked];"
            f"[{voice_label}_mix][ducked]amix=inputs=2:duration=first:"
            f"dropout_transition=2[{output_label}]"
        )
