from app.application.services.provider_performance_learning import (
    ProviderPerformanceLearning,
    ProviderPerformanceObservation,
)


def _obs(
    sequence: int,
    provider: str,
    *,
    success: bool = True,
    latency_ms: int = 1000,
    quality_score: float | None = None,
) -> ProviderPerformanceObservation:
    return ProviderPerformanceObservation(
        sequence=sequence,
        provider=provider,
        capability="TTS",
        operation="synthesize",
        success=success,
        latency_ms=latency_ms,
        quality_score=quality_score,
    )


def test_learning_requires_minimum_samples() -> None:
    learner = ProviderPerformanceLearning(minimum_samples=3)
    learned = learner.learn((_obs(1, "fish_audio"),))

    assert learned["fish_audio"].usable is False
    assert learner.ranking_score("fish_audio", learned=learned) == 1.0


def test_learning_is_capability_and_operation_scoped() -> None:
    learner = ProviderPerformanceLearning(minimum_samples=2)
    observations = (
        _obs(1, "fish_audio"),
        _obs(2, "fish_audio"),
        ProviderPerformanceObservation(
            sequence=3,
            provider="fish_audio",
            capability="TEXT_GENERATION",
            operation="generate",
            success=False,
            latency_ms=9000,
        ),
    )

    learned = learner.learn(
        observations,
        capability="TTS",
        operation="synthesize",
    )

    assert learned["fish_audio"].sample_count == 2
    assert learned["fish_audio"].success_rate == 1.0


def test_learning_prefers_recent_provider_outcomes() -> None:
    learner = ProviderPerformanceLearning(
        minimum_samples=2,
        recency_decay=0.5,
        quality_weight=0.0,
    )
    observations = (
        _obs(1, "provider_a", success=False, latency_ms=1000),
        _obs(2, "provider_a", success=True, latency_ms=1000),
    )

    learned = learner.learn(observations)

    assert learned["provider_a"].success_rate > 0.5


def test_learning_uses_quality_when_available() -> None:
    learner = ProviderPerformanceLearning(minimum_samples=2, quality_weight=0.5)
    observations = (
        _obs(1, "provider_a", quality_score=90.0),
        _obs(2, "provider_a", quality_score=90.0),
        _obs(1, "provider_b", quality_score=50.0),
        _obs(2, "provider_b", quality_score=50.0),
    )

    learned = learner.learn(observations)

    assert learner.ranking_score("provider_a", learned=learned) > learner.ranking_score(
        "provider_b", learned=learned
    )


def test_unknown_provider_keeps_deterministic_fallback() -> None:
    learner = ProviderPerformanceLearning()
    assert learner.ranking_score("unknown", learned={}) == 1.0
