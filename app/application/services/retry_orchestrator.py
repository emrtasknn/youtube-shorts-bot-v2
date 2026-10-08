from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from app.application.services.video_judge import VideoJudgeReport


class RetryAction(StrEnum):
    RESELECT_VISUALS = "reselect_visuals"
    REPAIR_AUDIO = "repair_audio"
    RECONCILE_TIMELINE = "reconcile_timeline"
    REGENERATE_VIDEO = "regenerate_video"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class RetryPlan:
    attempt: int
    max_attempts: int
    actions: tuple[RetryAction, ...]
    reasons: tuple[str, ...]
    retryable: bool
    terminal_reason: str | None = None

    @property
    def exhausted(self) -> bool:
        return self.attempt >= self.max_attempts


@dataclass(frozen=True, slots=True)
class RetryDecision:
    plan: RetryPlan
    next_status: str


class JudgeDrivenRetryOrchestrator:
    """Bounded retry policy derived from the automated judge report.

    The orchestrator owns *what* should be retried and *when to stop*.
    Execution remains in the generation pipeline so provider clients and
    render resources are not duplicated here.
    """

    def __init__(self, *, max_attempts: int = 2) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._max_attempts = max_attempts

    def plan(
        self,
        report: VideoJudgeReport,
        *,
        attempt: int,
    ) -> RetryPlan:
        if attempt < 1:
            raise ValueError("attempt must be at least 1")

        reasons = tuple(report.retry_reasons)
        if report.decision != "RETRY":
            return RetryPlan(
                attempt=attempt,
                max_attempts=self._max_attempts,
                actions=(),
                reasons=reasons,
                retryable=False,
                terminal_reason=f"judge_decision:{report.decision}",
            )

        if attempt >= self._max_attempts:
            return RetryPlan(
                attempt=attempt,
                max_attempts=self._max_attempts,
                actions=(RetryAction.ESCALATE,),
                reasons=reasons,
                retryable=False,
                terminal_reason="retry_budget_exhausted",
            )

        actions: list[RetryAction] = []
        for reason in reasons:
            action = self._action_for_reason(reason)
            if action is not None and action not in actions:
                actions.append(action)

        if not actions:
            actions.append(RetryAction.REGENERATE_VIDEO)
        elif RetryAction.REGENERATE_VIDEO not in actions:
            actions.append(RetryAction.REGENERATE_VIDEO)

        return RetryPlan(
            attempt=attempt,
            max_attempts=self._max_attempts,
            actions=tuple(actions),
            reasons=reasons,
            retryable=True,
        )

    def decide(self, report: VideoJudgeReport, *, attempt: int) -> RetryDecision:
        plan = self.plan(report, attempt=attempt)
        return RetryDecision(
            plan=plan,
            next_status="RETRYING" if plan.retryable else (
                "FAILED_PERMANENT" if plan.exhausted else "UNCHANGED"
            ),
        )

    @staticmethod
    def _action_for_reason(reason: str) -> RetryAction | None:
        mapping = {
            "excessive_visual_fallbacks": RetryAction.RESELECT_VISUALS,
            "audio_qc_failed": RetryAction.REPAIR_AUDIO,
            "synchronization_failed": RetryAction.RECONCILE_TIMELINE,
        }
        return mapping.get(reason)

    @property
    def max_attempts(self) -> int:
        return self._max_attempts
