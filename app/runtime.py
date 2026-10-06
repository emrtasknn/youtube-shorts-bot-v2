from __future__ import annotations

from dataclasses import dataclass

from app.application.ports.asset_downloader import AssetDownloader
from app.application.ports.stock_media import StockMediaGateway
from app.application.ports.text_generation import TextGenerationGateway
from app.application.ports.tts import TTSGateway
from app.application.ports.video_engine import VideoEngine
from app.config.settings import Settings
from app.infrastructure.providers.contracts import ProviderCapability
from app.infrastructure.providers.executor import ReliabilityExecutor
from app.infrastructure.providers.factory import build_provider_registry
from app.infrastructure.providers.gateways import (
    ProviderStockMediaGateway,
    ProviderTextGenerationGateway,
    ProviderTTSGateway,
)
from sqlalchemy.orm import Session

from app.infrastructure.providers.reliability import (
    ConcurrencyLimiter,
    CostTracker,
    DatabaseIdempotencyStore,
    IdempotencyStore,
    ProviderHealthManager,
    QuotaManager,
    RateLimiter,
    RetryManager,
    RetryPolicy,
    StrategyRouter,
)
from app.infrastructure.storage.http_downloader import HttpAssetDownloader
from app.infrastructure.video.ffmpeg import FFmpegVideoEngine


@dataclass(frozen=True, slots=True)
class RuntimeComponents:
    settings: Settings
    executor: ReliabilityExecutor
    text: TextGenerationGateway
    stock_media: StockMediaGateway
    tts: TTSGateway
    video_engine: VideoEngine
    downloader: AssetDownloader


def build_runtime(settings: Settings, session: Session | None = None) -> RuntimeComponents:
    registry = build_provider_registry(settings)
    providers = registry.providers_by_capability()

    text_providers = providers.get(ProviderCapability.TEXT_GENERATION, [])
    stock_providers = providers.get(ProviderCapability.STOCK_MEDIA, [])
    tts_providers = providers.get(ProviderCapability.TTS, [])

    if not text_providers:
        raise RuntimeError("No text-generation provider is enabled")
    if not stock_providers:
        raise RuntimeError("No stock-media provider is enabled")
    if not tts_providers:
        raise RuntimeError("No TTS provider is enabled")

    retry = RetryManager(
        RetryPolicy(
            max_attempts=3,
            base_delay_seconds=1.0,
            max_delay_seconds=30.0,
        )
    )
    health = ProviderHealthManager()
    rate_limiter = RateLimiter()
    concurrency = ConcurrencyLimiter()
    quota = QuotaManager()
    idempotency = DatabaseIdempotencyStore(session) if session is not None else IdempotencyStore()
    costs = CostTracker()

    for provider in {name for names in providers.values() for name in names}:
        health.configure(provider, failure_threshold=3, recovery_seconds=30.0)
        concurrency.configure(provider, limit=2)

    rate_limiter.configure("gemini", rate_per_second=1 / 2, capacity=2)
    rate_limiter.configure("groq", rate_per_second=1 / 2, capacity=2)
    rate_limiter.configure("pexels", rate_per_second=1 / 5, capacity=5)
    rate_limiter.configure("fish_audio", rate_per_second=1 / 2, capacity=2)

    executor = ReliabilityExecutor(
        registry=registry,
        retry=retry,
        health=health,
        rate_limiter=rate_limiter,
        concurrency=concurrency,
        quota=quota,
        idempotency=idempotency,
        costs=costs,
        router=StrategyRouter(health),
    )

    return RuntimeComponents(
        settings=settings,
        executor=executor,
        text=ProviderTextGenerationGateway(executor, text_providers),
        stock_media=ProviderStockMediaGateway(executor, stock_providers),
        tts=ProviderTTSGateway(executor, tts_providers),
        video_engine=FFmpegVideoEngine(),
        downloader=HttpAssetDownloader(),
    )
