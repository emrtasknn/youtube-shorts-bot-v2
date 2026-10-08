from pathlib import Path

import pytest

from app.application.services.retry_execution_engine import JudgeDrivenRetryExecutionEngine
from app.application.services.retry_orchestrator import RetryAction
from app.application.services.video_judge import VideoJudgeReport


def _report(
    *,
    decision: str,
    reasons: tuple[str, ...] = (),
    score: float = 90.0,
) -> VideoJudgeReport:
    return VideoJudgeReport(
        decision=decision,
        score=score,
        dimension_scores={"visual": score},
        failures=(),
        warnings=(),
        retry_reasons=reasons,
        evaluated_path=str(Path("storage/renders/test.mp4")),
    )


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[int, tuple[RetryAction, ...]]] = []

    async def execute(
        self,
        *,
        actions: tuple[RetryAction, ...],
        attempt: int,
    ) -> VideoJudgeReport:
        self.calls.append((attempt, actions))
        return _report(decision="PASS")


@pytest.mark.asyncio
async def test_retry_engine_executes_targeted_attempt_and_stops_on_pass() -> None:
    executor = FakeExecutor()
    engine = JudgeDrivenRetryExecutionEngine(executor=executor)

    result = await engine.execute(
        _report(
            decision="RETRY",
            reasons=("excessive_visual_fallbacks",),
            score=60.0,
        )
    )

    assert result.report.decision == "PASS"
    assert result.attempts[0].attempt == 2
    assert result.attempts[0].actions == (
        RetryAction.RESELECT_VISUALS,
        RetryAction.REGENERATE_VIDEO,
    )
    assert result.attempts[0].duration_seconds >= 0
    assert executor.calls == [
        (
            2,
            (
                RetryAction.RESELECT_VISUALS,
                RetryAction.REGENERATE_VIDEO,
            ),
        )
    ]
    assert not result.exhausted


@pytest.mark.asyncio
async def test_retry_engine_reuses_successful_checkpoint_bundle() -> None:
    class RetryThenPass(FakeExecutor):
        async def execute(
            self,
            *,
            actions: tuple[RetryAction, ...],
            attempt: int,
        ) -> VideoJudgeReport:
            self.calls.append((attempt, actions))
            if attempt == 2:
                return _report(
                    decision="RETRY",
                    reasons=("excessive_visual_fallbacks",),
                    score=70.0,
                )
            return _report(decision="PASS", score=80.0)

    executor = RetryThenPass()
    engine = JudgeDrivenRetryExecutionEngine(executor=executor)

    result = await engine.execute(
        _report(
            decision="RETRY",
            reasons=("excessive_visual_fallbacks",),
            score=60.0,
        )
    )

    assert result.attempts[0].actions == (
        RetryAction.RESELECT_VISUALS,
        RetryAction.REGENERATE_VIDEO,
    )
    assert result.attempts[1].reused_checkpoint_actions == (RetryAction.RESELECT_VISUALS,)
    assert result.attempts[1].actions == (RetryAction.REGENERATE_VIDEO,)
    assert result.report.decision == "PASS"


@pytest.mark.asyncio
async def test_retry_engine_executes_second_attempt_then_escalates() -> None:
    class AlwaysRetry(FakeExecutor):
        async def execute(
            self,
            *,
            actions: tuple[RetryAction, ...],
            attempt: int,
        ) -> VideoJudgeReport:
            self.calls.append((attempt, actions))
            return _report(
                decision="RETRY",
                reasons=("audio_qc_failed",),
                score=60.0,
            )

    executor = AlwaysRetry()
    engine = JudgeDrivenRetryExecutionEngine(executor=executor)

    result = await engine.execute(
        _report(
            decision="RETRY",
            reasons=("audio_qc_failed",),
            score=60.0,
        )
    )

    assert result.report.decision == "RETRY"
    assert result.exhausted
    assert result.terminal_reason == "retry_budget_exhausted"
    assert [attempt for attempt, _ in executor.calls] == [2, 3]


@pytest.mark.asyncio
async def test_non_retry_report_never_executes() -> None:
    executor = FakeExecutor()
    engine = JudgeDrivenRetryExecutionEngine(executor=executor)

    result = await engine.execute(_report(decision="PASS"))

    assert result.report.decision == "PASS"
    assert result.attempts == ()
    assert executor.calls == []
