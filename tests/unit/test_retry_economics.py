from pathlib import Path

from app.application.services.retry_economics import RetryEconomicsPolicy
from app.application.services.retry_orchestrator import RetryAction, RetryPlan
from app.application.services.video_judge import VideoJudgeReport


def _report(
    *,
    score: float,
    reasons: tuple[str, ...],
    dimensions: dict[str, float],
) -> VideoJudgeReport:
    return VideoJudgeReport(
        decision="RETRY",
        score=score,
        dimension_scores=dimensions,
        failures=(),
        warnings=(),
        retry_reasons=reasons,
        evaluated_path=str(Path("storage/renders/test.mp4")),
    )


def test_economics_prefers_high_gain_low_cost_audio_repair() -> None:
    policy = RetryEconomicsPolicy()
    plan = RetryPlan(
        attempt=1,
        max_attempts=3,
        actions=(RetryAction.REPAIR_AUDIO, RetryAction.REGENERATE_VIDEO),
        reasons=("audio_qc_failed",),
        retryable=True,
    )

    decision = policy.rank(
        plan,
        report=_report(
            score=65.0,
            reasons=("audio_qc_failed",),
            dimensions={"audio": 50.0, "visual": 95.0},
        ),
    )

    assert decision.actions[0] == RetryAction.REPAIR_AUDIO
    assert decision.rankings[0].efficiency > decision.rankings[1].efficiency


def test_economics_prioritizes_visual_reselection_when_visual_deficit_is_large() -> None:
    policy = RetryEconomicsPolicy()
    plan = RetryPlan(
        attempt=1,
        max_attempts=3,
        actions=(RetryAction.RESELECT_VISUALS, RetryAction.REGENERATE_VIDEO),
        reasons=("excessive_visual_fallbacks",),
        retryable=True,
    )

    decision = policy.rank(
        plan,
        report=_report(
            score=65.0,
            reasons=("excessive_visual_fallbacks",),
            dimensions={"visual": 40.0, "audio": 95.0},
        ),
    )

    assert decision.actions[0] == RetryAction.RESELECT_VISUALS
    assert decision.rankings[0].expected_gain > decision.rankings[1].expected_gain


def test_economics_preserves_untouched_targeted_actions() -> None:
    policy = RetryEconomicsPolicy()
    plan = RetryPlan(
        attempt=1,
        max_attempts=3,
        actions=(RetryAction.REPAIR_AUDIO, RetryAction.REGENERATE_VIDEO),
        reasons=("audio_qc_failed",),
        retryable=True,
    )

    decision = policy.rank(
        plan,
        report=_report(
            score=70.0,
            reasons=("audio_qc_failed",),
            dimensions={"audio": 60.0, "visual": 95.0},
        ),
    )

    assert RetryAction.RESELECT_VISUALS in decision.preserved_actions
    assert RetryAction.RECONCILE_TIMELINE in decision.preserved_actions
