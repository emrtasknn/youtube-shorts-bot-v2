from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Protocol

from app.application.services.adaptive_retry_policy import (
    AdaptiveRetryDecision,
    AdaptiveRetryPolicy,
    RetryEffectivenessObservation,
)
from app.application.services.retry_economics import RetryEconomicsDecision, RetryEconomicsPolicy
from app.application.services.retry_orchestrator import (
    JudgeDrivenRetryOrchestrator,
    RetryAction,
    RetryPlan,
)
from app.application.services.video_judge import VideoJudgeReport


class RetryAttemptExecutor(Protocol):
    async def execute(
        self,
        *,
        actions: tuple[RetryAction, ...],
        attempt: int,
    ) -> VideoJudgeReport: ...


@dataclass(frozen=True, slots=True)
class RetryExecutionAttempt:
    attempt: int
    actions: tuple[RetryAction, ...]
    reasons: tuple[str, ...]
    decision: str
    score: float
    duration_seconds: float = 0.0
    reused_checkpoint_actions: tuple[RetryAction, ...] = ()


@dataclass(frozen=True, slots=True)
class RetryExecutionResult:
    report: VideoJudgeReport
    attempts: tuple[RetryExecutionAttempt, ...]
    exhausted: bool
    terminal_reason: str | None
    effectiveness: tuple[RetryEffectivenessObservation, ...] = ()
    adaptations: tuple[AdaptiveRetryDecision, ...] = ()
    economics: tuple[RetryEconomicsDecision, ...] = ()


class JudgeDrivenRetryExecutionEngine:
    """Executes bounded retry plans and re-judges each produced artifact.

    The executor owns actual provider, asset and render operations. The engine
    records measured runtime cost and reuses successful retry checkpoints by
    not re-executing an already successful action bundle on later attempts.
    """

    def __init__(
        self,
        *,
        orchestrator: JudgeDrivenRetryOrchestrator | None = None,
        executor: RetryAttemptExecutor | Callable[..., Awaitable[VideoJudgeReport]],
        policy: AdaptiveRetryPolicy | None = None,
        economics_policy: RetryEconomicsPolicy | None = None,
    ) -> None:
        self._orchestrator = orchestrator or JudgeDrivenRetryOrchestrator(max_attempts=3)
        self._executor = executor
        self._policy = policy or AdaptiveRetryPolicy()
        self._economics = economics_policy or RetryEconomicsPolicy()

    async def execute(
        self,
        report: VideoJudgeReport,
        *,
        attempt: int = 1,
    ) -> RetryExecutionResult:
        history: list[RetryExecutionAttempt] = []
        observations: list[RetryEffectivenessObservation] = []
        adaptations: list[AdaptiveRetryDecision] = []
        economics_history: list[RetryEconomicsDecision] = []
        checkpoint_actions: tuple[RetryAction, ...] = ()
        current = report
        current_attempt = attempt

        while current.decision == "RETRY":
            decision = self._orchestrator.decide(current, attempt=current_attempt)
            plan = decision.plan
            if not plan.retryable:
                return RetryExecutionResult(
                    report=current,
                    attempts=tuple(history),
                    exhausted=plan.exhausted,
                    terminal_reason=plan.terminal_reason,
                    effectiveness=tuple(observations),
                    adaptations=tuple(adaptations),
                    economics=tuple(economics_history),
                )

            adaptive = self._policy.adapt(plan, observations=tuple(observations))
            adaptations.append(adaptive)
            adapted_plan = RetryPlan(
                attempt=plan.attempt,
                max_attempts=plan.max_attempts,
                actions=adaptive.actions,
                reasons=plan.reasons,
                retryable=plan.retryable,
                terminal_reason=plan.terminal_reason,
            )
            economics = self._economics.rank(
                adapted_plan,
                report=current,
                observations=tuple(observations),
            )
            economics_history.append(economics)

            ranked_actions = economics.actions
            reusable = tuple(action for action in ranked_actions if action in checkpoint_actions)
            next_plan_actions = tuple(action for action in ranked_actions if action not in checkpoint_actions)
            if not next_plan_actions and ranked_actions:
                next_plan_actions = (RetryAction.REGENERATE_VIDEO,)
            next_attempt = current_attempt + 1

            started = monotonic()
            next_report = await self._execute_attempt(next_plan_actions, next_attempt)
            duration = monotonic() - started

            history.append(
                RetryExecutionAttempt(
                    attempt=next_attempt,
                    actions=next_plan_actions,
                    reasons=plan.reasons,
                    decision=current.decision,
                    score=current.score,
                    duration_seconds=round(duration, 4),
                    reused_checkpoint_actions=reusable,
                )
            )
            observation = self._policy.observe(
                previous=current,
                current=next_report,
                actions=next_plan_actions,
                attempt=next_attempt,
                duration_seconds=duration,
            )
            observations.append(observation)

            if observation.improved and next_plan_actions:
                checkpoint_actions = next_plan_actions
            current = next_report
            current_attempt = next_attempt

        return RetryExecutionResult(
            report=current,
            attempts=tuple(history),
            exhausted=False,
            terminal_reason=None,
            effectiveness=tuple(observations),
            adaptations=tuple(adaptations),
            economics=tuple(economics_history),
        )

    async def _execute_attempt(
        self,
        actions: tuple[RetryAction, ...],
        attempt: int,
    ) -> VideoJudgeReport:
        execute = self._executor.execute if hasattr(self._executor, "execute") else self._executor
        return await execute(actions=actions, attempt=attempt)

    @property
    def max_attempts(self) -> int:
        return self._orchestrator.max_attempts
