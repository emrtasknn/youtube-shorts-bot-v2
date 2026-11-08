"""Build Studio services from settings."""

from __future__ import annotations

from pathlib import Path

from app.config.settings import Settings
from app.studio.llm import FallbackLLM, GeminiLLM, GroqLLM, JsonLLM
from app.studio.models import ProjectStore
from app.studio.publisher import StudioYouTube
from app.studio.store_sql import SqlProjectStore
from app.studio.tts import ChainTTS, EmaLightningTTS, FishAudioTTS, PiperTTS, TTSBackend


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


def build_tts(settings: Settings, override: str = "") -> ChainTTS:
    backends: list[TTSBackend] = []
    for name in [p.strip() for p in (override or settings.studio_tts).split(",") if p.strip()]:
        if name == "ema":
            backends.append(
                EmaLightningTTS(
                    speed=settings.studio_ema_speed,
                    seed=settings.studio_ema_seed,
                    device=settings.studio_ema_device,
                )
            )
        elif name == "fish" and settings.fish_audio_api_key:
            backends.append(
                FishAudioTTS(
                    settings.fish_audio_api_key,
                    model=settings.fish_audio_model,
                    reference_id=settings.fish_audio_reference_id,
                    base_url=settings.fish_audio_base_url,
                )
            )
        elif name == "piper" and settings.studio_piper_model_dir:
            backends.append(PiperTTS(Path(settings.studio_piper_model_dir)))
    return ChainTTS(backends)


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
