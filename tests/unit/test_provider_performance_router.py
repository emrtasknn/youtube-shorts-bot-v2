from app.application.services.provider_performance_learning import (
    ProviderPerformanceLearning,
    ProviderPerformanceObservation,
)
from app.infrastructure.providers.reliability import ProviderHealthManager, StrategyRouter


def test_router_uses_learned_provider_performance_without_breaking_order() -> None:
    learning = ProviderPerformanceLearning(minimum_samples=2, quality_weight=0.0)
    router = StrategyRouter(
        ProviderHealthManager(),
        performance_learning=learning,
    )
    observations = (
        ProviderPerformanceObservation(1, "slow", "TTS", "synthesize", True, 9000),
        ProviderPerformanceObservation(2, "slow", "TTS", "synthesize", True, 9000),
        ProviderPerformanceObservation(1, "fast", "TTS", "synthesize", True, 500),
        ProviderPerformanceObservation(2, "fast", "TTS", "synthesize", True, 500),
    )

    assert router.route(
        ["slow", "fast"],
        observations=observations,
        capability="TTS",
        operation="synthesize",
    ) == "fast"


def test_router_falls_back_to_declared_order_without_learning() -> None:
    router = StrategyRouter(ProviderHealthManager())

    assert router.route(["first", "second"]) == "first"
