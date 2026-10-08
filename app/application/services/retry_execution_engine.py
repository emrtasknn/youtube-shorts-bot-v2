from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.application.services.adaptive_retry_policy import (
    AdaptiveRetryPolicy,
    RetryEffectivenessObservation,
)
from app.application.services.retry_orchestrator import (
    JudgeDrivenRetryOrchestrator,
    RetryAction,
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


@dataclass(frozen=True, slots=True)
class RetryExecutionResult:
    report: VideoJudgeReport
    attempts: tuple[RetryExecutionAttempt, ...]
    exhausted: bool
    terminal_reason: str | None


class JudgeDrivenRetryExecutionEngine:
    """Executes bounded retry plans and re-judges each produced artifact.

    The engine owns retry-loop control only. The injected executor owns actual
    provider, asset and render operations, keeping resource ownership in the
    generation pipeline.
    """

    def __init__(
        self,
        *,
        orchestrator: JudgeDrivenRetryOrchestrator | None = None,
        executor: RetryAttemptExecutor | Callable[..., Awaitable[VideoJudgeReport]],
        policy: AdaptiveRetryPolicy | None = None,
    ) -> None:
        self._orchestrator = orchestrator or JudgeDrivenRetryOrchestrator(max_attempts=2)
        self._executor = executor
        self._policy = policy or AdaptiveRetryPolicy()

    async def execute(
        self,
        report: VideoJudgeReport,
        *,
        attempt: int = 1,
    ) -> RetryExecutionResult:
        history: list[RetryExecutionAttempt] = []
        observations: list[RetryEffectivenessObservation] = []
        current = report
        current_attempt = attempt

        while current.decision == "RETRY":
            decision = self._orchestrator.decide(
                current,
                attempt=current_attempt,
            )
            plan = decision.plan
            if not plan.retryable:
                return RetryExecutionResult(
                    report=current,
                    attempts=tuple(history),
                    exhausted=plan.exhausted,
                    terminal_reason=plan.terminal_reason,
                )

            adaptive = self._policy.adapt(
                plan,
                observations=tuple(observations),
            )
            next_plan_actions = adaptive.actions

            next_attempt = current_attempt + 1
            history.append(
                RetryExecutionAttempt(
                    attempt=next_attempt,
                    actions=next_plan_actions,
                    reasons=plan.reasons,
                    decision=current.decision,
                    score=current.score,
                )
            )
            current = await self._execute_attempt(
                next_plan_actions,
                next_attempt,
            )
            observations.append(
                self._policy.observe(
                    previous=report,
                    current=current,
                    actions=next_plan_actions,
                    attempt=next_attempt,
                )
            )
            report = current
            current_attempt = next_attempt

        return RetryExecutionResult(
            report=current,
            attempts=tuple(history),
            exhausted=False,
            terminal_reason=None,
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
