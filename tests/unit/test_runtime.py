from app.config.settings import Settings
from app.infrastructure.providers.contracts import ProviderCapability
from app.runtime import build_runtime


def test_build_runtime_registers_enabled_providers() -> None:
    settings = Settings(
        pexels_enabled=True,
        pexels_api_key="pexels-test",
        gemini_enabled=True,
        gemini_api_key="gemini-test",
        fish_audio_enabled=True,
        fish_audio_api_key="fish-test",
    )

    runtime = build_runtime(settings)

    assert runtime.executor.registry.get("gemini").capabilities == frozenset(
        {ProviderCapability.TEXT_GENERATION}
    )
    assert runtime.executor.registry.get("pexels").capabilities == frozenset(
        {ProviderCapability.STOCK_MEDIA}
    )
    assert runtime.executor.registry.get("fish_audio").capabilities == frozenset(
        {ProviderCapability.TTS}
    )


def test_build_runtime_rejects_missing_required_provider() -> None:
    settings = Settings(
        pexels_enabled=True,
        pexels_api_key="pexels-test",
        gemini_enabled=True,
        gemini_api_key="gemini-test",
        fish_audio_enabled=False,
    )

    try:
        build_runtime(settings)
    except RuntimeError as exc:
        assert str(exc) == "No TTS provider is enabled"
    else:
        raise AssertionError("build_runtime should reject a missing TTS provider")
