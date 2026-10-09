from app.config.settings import Settings
from app.infrastructure.providers.contracts import (
    ProviderCapability,
    ProviderDescriptor,
)
from app.infrastructure.providers.fish_audio import FishAudioTTSProvider
from app.infrastructure.providers.gemini import GeminiTextProvider
from app.infrastructure.providers.groq import GroqTextProvider
from app.infrastructure.providers.pexels import PexelsStockMediaProvider
from app.infrastructure.providers.registry import ProviderRegistry
from app.infrastructure.providers.wikimedia_commons import WikimediaCommonsProvider


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry()

    # Pexels remains the primary general-purpose stock source when configured.
    if settings.pexels_enabled and settings.pexels_api_key:
        registry.register(
            PexelsStockMediaProvider(
                settings.pexels_api_key,
                base_url=settings.pexels_base_url,
                timeout_seconds=settings.pexels_timeout_seconds,
            )
        )

    # Commons is public and keyless; retrieval selects it explicitly for archives.
    registry.register(
        WikimediaCommonsProvider(timeout_seconds=settings.wikimedia_commons_timeout_seconds),
        descriptor=ProviderDescriptor(
            "wikimedia_commons",
            frozenset({ProviderCapability.STOCK_MEDIA}),
            priority=10,
        ),
    )

    if settings.gemini_enabled and settings.gemini_api_key:
        registry.register(
            GeminiTextProvider(
                settings.gemini_api_key,
                base_url=settings.gemini_base_url,
                model=settings.gemini_model,
                timeout_seconds=settings.gemini_timeout_seconds,
            )
        )

    if settings.groq_enabled and settings.groq_api_key:
        registry.register(
            GroqTextProvider(
                settings.groq_api_key,
                base_url=settings.groq_base_url,
                model=settings.groq_model,
                timeout_seconds=settings.groq_timeout_seconds,
            )
        )

    if settings.fish_audio_enabled and settings.fish_audio_api_key:
        registry.register(
            FishAudioTTSProvider(
                settings.fish_audio_api_key,
                base_url=settings.fish_audio_base_url,
                model=settings.fish_audio_model,
                format=settings.fish_audio_format,
                reference_id=settings.fish_audio_reference_id or None,
                timeout_seconds=settings.fish_audio_timeout_seconds,
            )
        )

    return registry
