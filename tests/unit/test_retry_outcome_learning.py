from app.application.services.retry_orchestrator import RetryAction
from app.application.services.retry_outcome_learning import (
    RetryOutcomeLearning,
    RetryOutcomeObservation,
)


def test_learning_requires_minimum_isolated_samples() -> None:
    learner = RetryOutcomeLearning(minimum_samples=2)
    learned = learner.learn(
        (
            RetryOutcomeObservation(
                sequence=1,
                action=RetryAction.REPAIR_AUDIO,
                score_delta=8.0,
                duration_seconds=2.0,
                improved=True,
            ),
        )
    )

    assert learned[RetryAction.REPAIR_AUDIO].usable is False
    assert learner.expected_gain_multiplier(
        RetryAction.REPAIR_AUDIO,
        learned=learned,
    ) == 1.0


def test_learning_uses_recency_weighted_success_and_gain() -> None:
    learner = RetryOutcomeLearning(minimum_samples=2, recency_decay=0.5)
    learned = learner.learn(
        (
            RetryOutcomeObservation(
                sequence=1,
                action=RetryAction.REPAIR_AUDIO,
                score_delta=1.0,
                duration_seconds=3.0,
                improved=True,
            ),
            RetryOutcomeObservation(
                sequence=2,
                action=RetryAction.REPAIR_AUDIO,
                score_delta=10.0,
                duration_seconds=2.0,
                improved=True,
            ),
        )
    )

    evidence = learned[RetryAction.REPAIR_AUDIO]
    assert evidence.usable
    assert evidence.success_rate == 1.0
    assert evidence.average_gain > 1.0
    assert evidence.median_duration_seconds == 2.5
    assert evidence.confidence == 1.0


def test_learning_ignores_non_isolated_bundle_evidence() -> None:
    learner = RetryOutcomeLearning(minimum_samples=2)
    from app.application.services.adaptive_retry_policy import RetryEffectivenessObservation

    observations = (
        RetryEffectivenessObservation(
            attempt=2,
            actions=(RetryAction.REPAIR_AUDIO, RetryAction.REGENERATE_VIDEO),
            before_score=60.0,
            after_score=80.0,
            score_delta=20.0,
            improved=True,
            dimension_deltas={"audio": 20.0},
            duration_seconds=3.0,
        ),
    )

    isolated = tuple(
        RetryOutcomeObservation(
            sequence=index,
            action=observation.actions[0],
            score_delta=observation.score_delta,
            duration_seconds=observation.duration_seconds,
            improved=observation.improved,
        )
        for index, observation in enumerate(observations, start=1)
        if len(observation.actions) == 1
    )

    assert learner.learn(isolated) == {}


def test_learning_neutralizes_sparse_or_weak_evidence() -> None:
    learner = RetryOutcomeLearning(minimum_samples=2)
    learned = learner.learn(
        (
            RetryOutcomeObservation(
                sequence=1,
                action=RetryAction.RESELECT_VISUALS,
                score_delta=-4.0,
                duration_seconds=2.0,
                improved=False,
            ),
            RetryOutcomeObservation(
                sequence=2,
                action=RetryAction.RESELECT_VISUALS,
                score_delta=0.0,
                duration_seconds=2.0,
                improved=False,
            ),
        )
    )

    evidence = learned[RetryAction.RESELECT_VISUALS]
    assert evidence.usable
    assert evidence.success_rate == 0.0
    assert learner.expected_gain_multiplier(
        RetryAction.RESELECT_VISUALS,
        learned=learned,
    ) == 0.5
