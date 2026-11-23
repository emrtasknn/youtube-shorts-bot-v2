"""Build Studio services from settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config.settings import Settings
from app.studio.llm import FallbackLLM, GeminiLLM, GroqLLM, JsonLLM
from app.studio.models import ProjectStore
from app.studio.publisher import StudioYouTube
from app.studio.store_sql import SqlProjectStore
from app.studio.tts import (
    ChainTTS,
    EmaLightningTTS,
    FishAudioTTS,
    PiperTTS,
    TTSBackend,
    TTSError,
    VoiceCast,
    VoiceRole,
)


def build_store(settings: Settings) -> ProjectStore | SqlProjectStore:
    """``STUDIO_STORE=db`` keeps projects in DATABASE_URL (survives restarts / free hosts)."""
    if settings.studio_store.strip().lower() == "db":
        return SqlProjectStore.from_url(settings.database_url, Path(settings.studio_dir))
    return ProjectStore(Path(settings.studio_dir))


def build_llm(settings: Settings) -> FallbackLLM:
    providers: list[JsonLLM] = []
    for name in [p.strip() for p in settings.studio_llm.split(",") if p.strip()]:
        if name == "groq" and settings.groq_api_key:
            providers.append(
                GroqLLM(
                    settings.groq_api_key,
                    model=settings.studio_groq_model or settings.groq_model,
                    base_url=settings.groq_base_url,
                )
            )
        elif name == "gemini" and settings.gemini_api_key:
            providers.append(
                GeminiLLM(
                    settings.gemini_api_key,
                    model=settings.studio_gemini_model or settings.gemini_model,
                    base_url=settings.gemini_base_url,
                )
            )
    return FallbackLLM(providers)


def _backends(
    settings: Settings, names: str, opts: dict[str, Any] | None = None
) -> list[TTSBackend]:
    """Backends named in ``names`` (comma separated), with per-role overrides in ``opts``."""
    o = opts or {}
    backends: list[TTSBackend] = []
    for name in [p.strip() for p in names.split(",") if p.strip()]:
        if name == "ema":
            backends.append(
                EmaLightningTTS(
                    speed=float(o.get("ema_speed", settings.studio_ema_speed)),
                    seed=int(o.get("ema_seed", settings.studio_ema_seed)),
                    device=settings.studio_ema_device,
                )
            )
        elif name == "fish" and settings.fish_audio_api_key:
            backends.append(
                FishAudioTTS(
                    settings.fish_audio_api_key,
                    model=str(o.get("fish_model", settings.fish_audio_model)),
                    reference_id=str(o.get("reference_id", settings.fish_audio_reference_id)),
                    base_url=settings.fish_audio_base_url,
                )
            )
        elif name == "piper":
            model_dir = str(o.get("piper_model_dir", settings.studio_piper_model_dir))
            if model_dir:
                backends.append(PiperTTS(Path(model_dir), speed=float(o.get("piper_speed", 1.1))))
    return backends


def build_tts(settings: Settings, override: str = "") -> ChainTTS:
    return ChainTTS(_backends(settings, override or settings.studio_tts))


VOICE_KEYS = {
    "tts",
    "reference_id",
    "fish_model",
    "ema_speed",
    "ema_seed",
    "piper_model_dir",
    "piper_speed",
    "effect",
    "gain_db",
}


def parse_voice_specs(raw: str) -> dict[str, dict[str, Any]]:
    """Validate ``STUDIO_VOICES``; errors name the role and key so they are easy to fix."""
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise TTSError(f"STUDIO_VOICES geçerli JSON değil: {exc}") from exc
    if not isinstance(data, dict):
        raise TTSError('STUDIO_VOICES bir JSON nesnesi olmalı: {"rol": {"tts": "fish"}}')
    specs: dict[str, dict[str, Any]] = {}
    for role, spec in data.items():
        if not isinstance(spec, dict):
            raise TTSError(f"STUDIO_VOICES '{role}': ayarlar bir JSON nesnesi olmalı")
        extra = set(spec) - VOICE_KEYS
        if extra:
            raise TTSError(
                f"STUDIO_VOICES '{role}': bilinmeyen alan {', '.join(sorted(extra))} "
                f"(geçerli: {', '.join(sorted(VOICE_KEYS))})"
            )
        if not str(spec.get("tts", "")).strip():
            raise TTSError(f"STUDIO_VOICES '{role}': 'tts' gerekli (ema, fish, piper)")
        specs[str(role)] = spec
    return specs


def build_cast(settings: Settings, override: str = "") -> VoiceCast:
    """Main narrator from ``STUDIO_TTS`` (or ``override``), extra roles from ``STUDIO_VOICES``."""
    roles: list[VoiceRole] = []
    for role, spec in parse_voice_specs(settings.studio_voices).items():
        backends = _backends(settings, str(spec["tts"]), spec)
        if not backends:
            raise TTSError(
                f"'{role}' sesi için kullanılabilir TTS yok ({spec['tts']}): "
                "API anahtarı / model klasörü eksik olabilir"
            )
        roles.append(
            VoiceRole(
                role,
                ChainTTS(backends),
                gain_db=float(spec.get("gain_db", 0.0)),
                effect=str(spec.get("effect", "")),
            )
        )
    return VoiceCast(build_tts(settings, override), roles)


def build_youtube(settings: Settings) -> StudioYouTube | None:
    if not (
        settings.youtube_client_id
        and settings.youtube_client_secret
        and settings.youtube_refresh_token
    ):
        return None
    return StudioYouTube(
        settings.youtube_client_id,
        settings.youtube_client_secret,
        settings.youtube_refresh_token,
        category_id=settings.youtube_category_id,
    )
