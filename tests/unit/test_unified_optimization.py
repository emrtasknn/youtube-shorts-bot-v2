from app.application.services.provider_performance_learning import ProviderPerformanceObservation
from app.application.services.retry_orchestrator import RetryAction, RetryPlan
from app.application.services.unified_optimization import (
    ProviderCostObservation,
    UnifiedOptimization,
)
from app.application.services.video_judge import VideoJudgeReport


def _report() -> VideoJudgeReport:
    return VideoJudgeReport(
        decision="RETRY",
        score=65.0,
        dimension_scores={
            "technical": 90.0,
            "narrative": 90.0,
            "visual": 40.0,
            "audio": 90.0,
            "captions": 90.0,
            "synchronization": 90.0,
            "product": 90.0,
        },
        failures=(),
        warnings=(),
        retry_reasons=("excessive_visual_fallbacks",),
        evaluated_path="test.mp4",
    )


def _plan() -> RetryPlan:
    return RetryPlan(
        actions=(RetryAction.RESELECT_VISUALS, RetryAction.REPAIR_AUDIO),
        reasons=("excessive_visual_fallbacks",),
        retryable=True,
        attempt=1,
        max_attempts=3,
    )


def test_cold_start_preserves_action_order_and_neutral_provider_signals():
    decisions = UnifiedOptimization().rank(
        _plan(),
        report=_report(),
        providers=("slow", "fast"),
        capability="IMAGE_SEARCH",
        operation="search",
    )
    assert decisions
    assert all(item.provider in {"slow", "fast"} for item in decisions)
    assert all(item.provider_cost is None for item in decisions)


def test_provider_learning_and_measured_cost_can_change_winner():
    observations = tuple(
        ProviderPerformanceObservation(
            sequence=index,
            provider="fast",
            capability="IMAGE_SEARCH",
            operation="search",
            success=True,
            latency_ms=100,
            quality_score=0.95,
        )
        for index in range(1, 4)
    ) + tuple(
        ProviderPerformanceObservation(
            sequence=index,
            provider="slow",
            capability="IMAGE_SEARCH",
            operation="search",
            success=True,
            latency_ms=1000,
            quality_score=0.70,
        )
        for index in range(4, 7)
    )
    costs = (
        *(ProviderCostObservation(i, "fast", "IMAGE_SEARCH", "search", 0.02) for i in range(1, 4)),
        *(ProviderCostObservation(i, "slow", "IMAGE_SEARCH", "search", 0.20) for i in range(4, 7)),
    )
    decisions = UnifiedOptimization().rank(
        _plan(),
        report=_report(),
        providers=("slow", "fast"),
        provider_observations=observations,
        provider_cost_observations=costs,
        capability="IMAGE_SEARCH",
        operation="search",
    )
    assert decisions[0].provider == "fast"


def test_scoped_provider_evidence_does_not_leak_between_operations():
    observations = tuple(
        ProviderPerformanceObservation(
            sequence=index,
            provider="provider-a",
            capability="TTS",
            operation="synthesize",
            success=True,
            latency_ms=100,
            quality_score=0.9,
        )
        for index in range(1, 4)
    )
    decisions = UnifiedOptimization().rank(
        _plan(),
        report=_report(),
        providers=("provider-a", "provider-b"),
        provider_observations=observations,
        capability="IMAGE_SEARCH",
        operation="search",
    )
    provider_a = [item for item in decisions if item.provider == "provider-a"]
    assert provider_a
    assert all(item.provider_performance is None for item in provider_a)


def test_sparse_cost_evidence_is_neutral():
    costs = (ProviderCostObservation(1, "fast", "IMAGE_SEARCH", "search", 0.01),)
    decisions = UnifiedOptimization().rank(
        _plan(),
        report=_report(),
        providers=("fast", "slow"),
        provider_cost_observations=costs,
        capability="IMAGE_SEARCH",
        operation="search",
    )
    fast = [item for item in decisions if item.provider == "fast"]
    assert fast
    assert all(item.provider_cost is not None and not item.provider_cost.usable for item in fast)


def test_negative_cost_is_ignored():
    costs = (
        ProviderCostObservation(1, "fast", "IMAGE_SEARCH", "search", -1.0),
        ProviderCostObservation(2, "fast", "IMAGE_SEARCH", "search", -2.0),
    )
    decisions = UnifiedOptimization().rank(
        _plan(),
        report=_report(),
        providers=("fast",),
        provider_cost_observations=costs,
        capability="IMAGE_SEARCH",
        operation="search",
    )
    assert decisions[0].provider_cost is None
