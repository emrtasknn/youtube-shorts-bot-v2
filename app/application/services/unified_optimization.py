from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from app.application.services.provider_performance_learning import (
    ProviderPerformance,
    ProviderPerformanceLearning,
    ProviderPerformanceObservation,
)
from app.application.services.retry_economics import RetryActionEconomics, RetryEconomicsPolicy
from app.application.services.retry_orchestrator import RetryAction, RetryPlan
from app.application.services.video_judge import VideoJudgeReport


@dataclass(frozen=True, slots=True)
class ProviderCostObservation:
    sequence: int
    provider: str
    capability: str
    operation: str
    cost: float


@dataclass(frozen=True, slots=True)
class ProviderCost:
    provider: str
    median_cost: float
    sample_count: int
    confidence: float
    usable: bool


@dataclass(frozen=True, slots=True)
class UnifiedDecision:
    action: RetryAction
    provider: str | None
    action_economics: RetryActionEconomics
    provider_performance: ProviderPerformance | None
    provider_cost: ProviderCost | None
    decision_score: float
    confidence: float
    reason: str


class UnifiedOptimization:
    """Chooses retry work and provider using one bounded decision score.

    The engine does not replace M30-M37. It composes their learned signals:
    action gain/cost, provider reliability/latency/quality and measured
    provider runtime cost. Sparse evidence remains neutral.
    """

    def __init__(
        self,
        *,
        retry_economics: RetryEconomicsPolicy | None = None,
        provider_learning: ProviderPerformanceLearning | None = None,
        minimum_cost_samples: int = 2,
        cost_weight: float = 0.25,
    ) -> None:
        if minimum_cost_samples < 1:
            raise ValueError("minimum_cost_samples must be positive")
        if not 0.0 <= cost_weight <= 1.0:
            raise ValueError("cost_weight must be between 0 and 1")
        self._retry_economics = retry_economics or RetryEconomicsPolicy()
        self._provider_learning = provider_learning or ProviderPerformanceLearning()
        self._minimum_cost_samples = minimum_cost_samples
        self._cost_weight = cost_weight

    def rank(
        self,
        plan: RetryPlan,
        *,
        report: VideoJudgeReport,
        providers: tuple[str, ...] = (),
        provider_observations: tuple[ProviderPerformanceObservation, ...] = (),
        provider_cost_observations: tuple[ProviderCostObservation, ...] = (),
        retry_observations=(),
        historical_retry_observations=(),
        capability: str | None = None,
        operation: str | None = None,
    ) -> tuple[UnifiedDecision, ...]:
        economics = self._retry_economics.rank(
            plan,
            report=report,
            observations=tuple(retry_observations),
            historical_observations=tuple(historical_retry_observations),
        )
        if not economics.rankings:
            return ()

        learned = self._provider_learning.learn(
            provider_observations,
            capability=capability,
            operation=operation,
        )
        costs = self._learn_provider_costs(
            provider_cost_observations,
            capability=capability,
            operation=operation,
        )
        decisions: list[UnifiedDecision] = []

        provider_choices = providers or (None,)
        for action_item in economics.rankings:
            for provider in provider_choices:
                performance = learned.get(provider) if provider is not None else None
                provider_cost = costs.get(provider) if provider is not None else None
                provider_multiplier = (
                    self._provider_learning.ranking_score(provider, learned=learned)
                    if provider is not None
                    else 1.0
                )
                cost_multiplier = self._cost_multiplier(provider_cost, costs)
                score = action_item.efficiency * provider_multiplier * cost_multiplier
                confidence = self._combined_confidence(
                    action_item,
                    performance,
                    provider_cost,
                )
                decisions.append(
                    UnifiedDecision(
                        action=action_item.action,
                        provider=provider,
                        action_economics=action_item,
                        provider_performance=performance,
                        provider_cost=provider_cost,
                        decision_score=round(score, 6),
                        confidence=round(confidence, 4),
                        reason=self._reason(
                            action_item,
                            performance,
                            provider_cost,
                            provider_multiplier,
                            cost_multiplier,
                        ),
                    )
                )

        return tuple(
            sorted(
                decisions,
                key=lambda item: (
                    -item.decision_score,
                    -item.confidence,
                    item.action.value,
                    item.provider or "",
                ),
            )
        )

    def _learn_provider_costs(
        self,
        observations: tuple[ProviderCostObservation, ...],
        *,
        capability: str | None,
        operation: str | None,
    ) -> dict[str, ProviderCost]:
        grouped: dict[str, list[ProviderCostObservation]] = {}
        for observation in observations:
            if observation.cost < 0:
                continue
            if capability is not None and observation.capability != capability:
                continue
            if operation is not None and observation.operation != operation:
                continue
            grouped.setdefault(observation.provider, []).append(observation)

        learned: dict[str, ProviderCost] = {}
        for provider, items in grouped.items():
            costs = [item.cost for item in items]
            usable = len(costs) >= self._minimum_cost_samples
            confidence = min(1.0, len(costs) / self._minimum_cost_samples)
            learned[provider] = ProviderCost(
                provider=provider,
                median_cost=round(median(costs), 6),
                sample_count=len(costs),
                confidence=round(confidence, 4),
                usable=usable,
            )
        return learned

    def _cost_multiplier(
        self,
        provider_cost: ProviderCost | None,
        all_costs: dict[str, ProviderCost],
    ) -> float:
        usable = [item.median_cost for item in all_costs.values() if item.usable and item.median_cost > 0]
        if provider_cost is None or not provider_cost.usable or not usable:
            return 1.0
        baseline = median(usable)
        if baseline <= 0:
            return 1.0
        ratio = baseline / max(provider_cost.median_cost, 1e-9)
        return max(
            0.75,
            min(1.25, 1.0 + (ratio - 1.0) * self._cost_weight),
        )

    def _combined_confidence(
        self,
        action: RetryActionEconomics,
        performance: ProviderPerformance | None,
        provider_cost: ProviderCost | None,
    ) -> float:
        signals = [0.5]
        if performance is not None and performance.usable:
            signals.append(performance.confidence)
        if provider_cost is not None and provider_cost.usable:
            signals.append(provider_cost.confidence)
        action_confidence = min(1.0, max(0.0, action.expected_gain / 40.0))
        signals.append(action_confidence)
        return sum(signals) / len(signals)

    def _reason(
        self,
        action: RetryActionEconomics,
        performance: ProviderPerformance | None,
        provider_cost: ProviderCost | None,
        provider_multiplier: float,
        cost_multiplier: float,
    ) -> str:
        parts = [f"action_efficiency={action.efficiency:.4f}"]
        if performance is not None and performance.usable:
            parts.append("provider_learning")
        if provider_cost is not None and provider_cost.usable:
            parts.append("measured_provider_cost")
        if provider_multiplier == 1.0 and cost_multiplier == 1.0:
            parts.append("neutral_sparse_evidence")
        return "ranked_by_" + "_and_".join(parts)
