from pathlib import Path

from app.application.services.retry_orchestrator import (
    JudgeDrivenRetryOrchestrator,
    RetryAction,
)
from app.application.services.video_judge import VideoJudgeReport


def _report(
    *,
    decision: str = "RETRY",
    reasons: tuple[str, ...] = ("excessive_visual_fallbacks",),
) -> VideoJudgeReport:
    return VideoJudgeReport(
        decision=decision,
        score=60.0,
        dimension_scores={"visual": 60.0},
        failures=(),
        warnings=(),
        retry_reasons=reasons,
        evaluated_path=str(Path("storage/renders/test.mp4")),
    )


def test_visual_retry_is_targeted_and_bounded() -> None:
    plan = JudgeDrivenRetryOrchestrator(max_attempts=2).plan(
        _report(),
        attempt=1,
    )

    assert plan.retryable
    assert plan.actions == (
        RetryAction.RESELECT_VISUALS,
        RetryAction.REGENERATE_VIDEO,
    )
    assert not plan.exhausted


def test_multiple_retry_reasons_deduplicate_actions() -> None:
    plan = JudgeDrivenRetryOrchestrator().plan(
        _report(
            reasons=("excessive_visual_fallbacks", "audio_qc_failed")
        ),
        attempt=1,
    )

    assert plan.actions == (
        RetryAction.RESELECT_VISUALS,
        RetryAction.REPAIR_AUDIO,
        RetryAction.REGENERATE_VIDEO,
    )


def test_retry_budget_exhaustion_escalates() -> None:
    plan = JudgeDrivenRetryOrchestrator(max_attempts=2).plan(
        _report(),
        attempt=2,
    )

    assert not plan.retryable
    assert plan.exhausted
    assert plan.actions == (RetryAction.ESCALATE,)
    assert plan.terminal_reason == "retry_budget_exhausted"


def test_non_retry_decision_is_not_replanned() -> None:
    plan = JudgeDrivenRetryOrchestrator().plan(
        _report(decision="PASS", reasons=()),
        attempt=1,
    )

    assert not plan.retryable
    assert plan.actions == ()
    assert plan.terminal_reason == "judge_decision:PASS"


def test_decide_exposes_retrying_status() -> None:
    decision = JudgeDrivenRetryOrchestrator().decide(_report(), attempt=1)

    assert decision.next_status == "RETRYING"
