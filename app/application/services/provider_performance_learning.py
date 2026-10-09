from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from statistics import median


@dataclass(frozen=True, slots=True)
class ProviderPerformanceObservation:
    sequence: int
    provider: str
    capability: str
    operation: str
    success: bool
    latency_ms: int
    quality_score: float | None = None


@dataclass(frozen=True, slots=True)
class ProviderPerformance:
    provider: str
    sample_count: int
    success_rate: float
    median_latency_ms: float
    average_quality_score: float | None
    confidence: float
    usable: bool


class ProviderPerformanceLearning:
    """Conservative, recency-weighted learning for provider selection."""

    def __init__(
        self,
        *,
        minimum_samples: int = 3,
        recency_decay: float = 0.9,
        quality_weight: float = 0.35,
    ) -> None:
        if minimum_samples < 1:
            raise ValueError("minimum_samples must be positive")
        if not 0.0 < recency_decay <= 1.0:
            raise ValueError("recency_decay must be in (0, 1]")
        if not 0.0 <= quality_weight <= 1.0:
            raise ValueError("quality_weight must be in [0, 1]")
        self._minimum_samples = minimum_samples
        self._recency_decay = recency_decay
        self._quality_weight = quality_weight

    def learn(
        self,
        observations: tuple[ProviderPerformanceObservation, ...],
        *,
        capability: str | None = None,
        operation: str | None = None,
    ) -> dict[str, ProviderPerformance]:
        filtered = tuple(
            item
            for item in observations
            if (capability is None or item.capability == capability)
            and (operation is None or item.operation == operation)
            and item.latency_ms >= 0
        )
        latest = max((item.sequence for item in filtered), default=0)
        providers = {item.provider for item in filtered}
        result: dict[str, ProviderPerformance] = {}

        for provider in providers:
            items = [item for item in filtered if item.provider == provider]
            weighted = [(item, self._weight(latest - item.sequence)) for item in items]
            weight_sum = sum(weight for _, weight in weighted)
            success_rate = (
                sum(weight for item, weight in weighted if item.success) / weight_sum
                if weight_sum
                else 0.0
            )
            latencies = [item.latency_ms for item in items if item.latency_ms > 0]
            quality_items = [
                (item, weight) for item, weight in weighted if item.quality_score is not None
            ]
            quality_weight_sum = sum(weight for _, weight in quality_items)
            quality = (
                sum(
                    weight * max(0.0, min(100.0, item.quality_score or 0.0))
                    for item, weight in quality_items
                )
                / quality_weight_sum
                if quality_weight_sum
                else None
            )
            result[provider] = ProviderPerformance(
                provider=provider,
                sample_count=len(items),
                success_rate=round(success_rate, 4),
                median_latency_ms=round(median(latencies), 2) if latencies else 0.0,
                average_quality_score=round(quality, 2) if quality is not None else None,
                confidence=round(min(1.0, len(items) / self._minimum_samples), 4),
                usable=len(items) >= self._minimum_samples,
            )

        return result

    def ranking_score(
        self,
        provider: str,
        *,
        learned: dict[str, ProviderPerformance],
    ) -> float:
        evidence = learned.get(provider)
        if evidence is None or not evidence.usable:
            return 1.0

        quality_signal = (
            evidence.average_quality_score / 100.0
            if evidence.average_quality_score is not None
            else 0.5
        )
        reliability = evidence.success_rate
        effectiveness = (
            1.0 - self._quality_weight
        ) * reliability + self._quality_weight * quality_signal
        latency_penalty = 1.0 / (1.0 + max(0.0, evidence.median_latency_ms) / 5000.0)
        raw = 0.5 + effectiveness * latency_penalty
        multiplier = 1.0 + (min(1.5, max(0.5, raw)) - 1.0) * evidence.confidence
        return round(min(1.25, max(0.75, multiplier)), 4)

    def _weight(self, age: int) -> float:
        return exp(age * log(self._recency_decay))
