import pytest

from app.domain.enums import (
    ApprovalStatus,
    ProviderHealthStatus,
    PublicationStatus,
    RunStatus,
    StageStatus,
)
from app.domain.state_machine import (
    CircuitBreaker,
    InvalidTransition,
    transition_approval,
    transition_publication,
    transition_run,
    transition_stage,
)


def test_run_happy_path_transition() -> None:
    assert transition_run(RunStatus.CREATED, RunStatus.QUEUED) == RunStatus.QUEUED
    assert transition_run(RunStatus.QUEUED, RunStatus.RUNNING) == RunStatus.RUNNING


def test_run_rejects_skipping_stage() -> None:
    with pytest.raises(InvalidTransition):
        transition_run(RunStatus.CREATED, RunStatus.SCRIPTING)


def test_stage_retry_loop() -> None:
    assert transition_stage(StageStatus.RUNNING, StageStatus.RETRY_WAIT) == StageStatus.RETRY_WAIT
    assert transition_stage(StageStatus.RETRY_WAIT, StageStatus.RUNNING) == StageStatus.RUNNING


def test_approval_edit_request_can_return_to_pending() -> None:
    assert (
        transition_approval(ApprovalStatus.PENDING, ApprovalStatus.EDIT_REQUESTED)
        == ApprovalStatus.EDIT_REQUESTED
    )
    assert (
        transition_approval(ApprovalStatus.EDIT_REQUESTED, ApprovalStatus.PENDING)
        == ApprovalStatus.PENDING
    )


def test_publication_is_idempotent_at_domain_level() -> None:
    with pytest.raises(InvalidTransition):
        transition_publication(PublicationStatus.PUBLISHED, PublicationStatus.UPLOADING)


def test_circuit_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2)
    breaker.record_failure()
    assert breaker.status == ProviderHealthStatus.DEGRADED
    breaker.record_failure()
    assert breaker.status == ProviderHealthStatus.OPEN
    breaker.record_success()
    assert breaker.status == ProviderHealthStatus.HEALTHY
