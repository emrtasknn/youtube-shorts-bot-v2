from pathlib import Path

import pytest

from app.application.services.adaptive_retry_policy import AdaptiveRetryPolicy
from app.application.services.retry_execution_engine import JudgeDrivenRetryExecutionEngine
from app.application.services.retry_orchestrator import RetryAction, RetryPlan
from app.application.services.video_judge import VideoJudgeReport


def report(
    *,
    decision: str,
    score: float,
    retry_reasons: tuple[str, ...] = (),
    dimensions: dict[str, float] | None = None,
) -> VideoJudgeReport:
    return VideoJudgeReport(
        decision=decision,
        score=score,
        dimension_scores=dimensions or {"visual": score, "audio": score},
        failures=(),
        warnings=(),
        retry_reasons=retry_reasons,
        evaluated_path=str(Path("storage/renders/test.mp4")),
    )


def test_policy_excludes_non_improving_targeted_action() -> None:
    policy = AdaptiveRetryPolicy(minimum_score_improvement=1.0)
    observation = policy.observe(
        previous=report(decision="RETRY", score=60.0),
        current=report(
            decision="RETRY",
            score=60.2,
            dimensions={"visual": 60.0, "audio": 60.4},
        ),
        actions=(RetryAction.REPAIR_AUDIO, RetryAction.REGENERATE_VIDEO),
        attempt=2,
    )

    decision = policy.adapt(
        RetryPlan(
            attempt=2,
            max_attempts=3,
            actions=(
                RetryAction.REPAIR_AUDIO,
                RetryAction.REGENERATE_VIDEO,
            ),
            reasons=("audio_qc_failed",),
            retryable=True,
        ),
        observations=(observation,),
    )

    assert decision.excluded_actions == (RetryAction.REPAIR_AUDIO,)
    assert decision.actions == (RetryAction.REGENERATE_VIDEO,)
    assert not observation.improved


def test_policy_keeps_action_that_improved_score() -> None:
    policy = AdaptiveRetryPolicy()
    observation = policy.observe(
        previous=report(decision="RETRY", score=60.0),
        current=report(decision="RETRY", score=66.0),
        actions=(RetryAction.RESELECT_VISUALS,),
        attempt=2,
    )
    decision = policy.adapt(
        RetryPlan(
            attempt=2,
            max_attempts=3,
            actions=(RetryAction.RESELECT_VISUALS, RetryAction.REGENERATE_VIDEO),
            reasons=("excessive_visual_fallbacks",),
            retryable=True,
        ),
        observations=(observation,),
    )
    assert decision.excluded_actions == ()
    assert RetryAction.RESELECT_VISUALS in decision.actions


@pytest.mark.asyncio
async def test_engine_records_effectiveness_and_changes_next_action() -> None:
    class AdaptiveExecutor:
        def __init__(self) -> None:
            self.calls: list[tuple[int, tuple[RetryAction, ...]]] = []

        async def execute(
            self,
            *,
            actions: tuple[RetryAction, ...],
            attempt: int,
        ) -> VideoJudgeReport:
            self.calls.append((attempt, actions))
            if attempt == 2:
                return report(
                    decision="RETRY",
                    score=60.0,
                    retry_reasons=("audio_qc_failed",),
                )
            return report(decision="PASS", score=90.0)

    executor = AdaptiveExecutor()
    engine = JudgeDrivenRetryExecutionEngine(
        orchestrator=__import__(
            "app.application.services.retry_orchestrator",
            fromlist=["JudgeDrivenRetryOrchestrator"],
        ).JudgeDrivenRetryOrchestrator(max_attempts=3),
        executor=executor,
    )
    result = await engine.execute(
        report(
            decision="RETRY",
            score=60.0,
            retry_reasons=("audio_qc_failed",),
        )
    )

    assert result.report.decision == "PASS"
    assert len(result.effectiveness) == 1
    assert result.effectiveness[0].score_delta == 0.0
    assert executor.calls[0][1] == (
        RetryAction.REPAIR_AUDIO,
        RetryAction.REGENERATE_VIDEO,
    )


def test_policy_rejects_negative_threshold() -> None:
    with pytest.raises(ValueError):
        AdaptiveRetryPolicy(minimum_score_improvement=-0.1)
