from app.config.settings import Settings
from app.infrastructure.providers.gemini import GeminiTextProvider
from app.infrastructure.providers.pexels import PexelsStockMediaProvider
from app.infrastructure.providers.registry import ProviderRegistry


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry()

    if settings.pexels_enabled and settings.pexels_api_key:
        registry.register(
            PexelsStockMediaProvider(
                settings.pexels_api_key,
                base_url=settings.pexels_base_url,
                timeout_seconds=settings.pexels_timeout_seconds,
            )
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

    return registry
