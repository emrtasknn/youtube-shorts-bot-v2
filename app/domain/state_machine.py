from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from app.domain.enums import (
    ApprovalStatus,
    PublicationStatus,
    RunStatus,
    StageStatus,
    ProviderHealthStatus,
)


class InvalidTransition(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.CREATED: frozenset({RunStatus.QUEUED, RunStatus.CANCELLED}),
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset({RunStatus.RESEARCHING, RunStatus.FAILED_RETRYABLE, RunStatus.FAILED_PERMANENT, RunStatus.CANCELLED}),
    RunStatus.RESEARCHING: frozenset({RunStatus.TOPIC_VALIDATION, RunStatus.FAILED_RETRYABLE, RunStatus.FAILED_PROVIDER}),
    RunStatus.TOPIC_VALIDATION: frozenset({RunStatus.SCRIPTING, RunStatus.FAILED_RETRYABLE, RunStatus.FAILED_PERMANENT}),
    RunStatus.SCRIPTING: frozenset({RunStatus.STORYBOARDING, RunStatus.FAILED_RETRYABLE, RunStatus.FAILED_PROVIDER}),
    RunStatus.STORYBOARDING: frozenset({RunStatus.ASSET_PLANNING, RunStatus.FAILED_RETRYABLE, RunStatus.FAILED_QC}),
    RunStatus.ASSET_PLANNING: frozenset({RunStatus.ASSET_GENERATION, RunStatus.FAILED_RETRYABLE, RunStatus.FAILED_PERMANENT}),
    RunStatus.ASSET_GENERATION: frozenset({RunStatus.TTS, RunStatus.FAILED_RETRYABLE, RunStatus.FAILED_PROVIDER, RunStatus.FAILED_QC}),
    RunStatus.TTS: frozenset({RunStatus.AUDIO_MIX, RunStatus.FAILED_RETRYABLE, RunStatus.FAILED_PROVIDER}),
    RunStatus.AUDIO_MIX: frozenset({RunStatus.RENDERING, RunStatus.FAILED_RETRYABLE, RunStatus.FAILED_QC}),
    RunStatus.RENDERING: frozenset({RunStatus.QC, RunStatus.FAILED_RETRYABLE}),
    RunStatus.QC: frozenset({RunStatus.READY_FOR_APPROVAL, RunStatus.FAILED_QC, RunStatus.FAILED_RETRYABLE}),
    RunStatus.READY_FOR_APPROVAL: frozenset({RunStatus.APPROVED, RunStatus.CANCELLED}),
    RunStatus.APPROVED: frozenset({RunStatus.PUBLISHING, RunStatus.CANCELLED}),
    RunStatus.PUBLISHING: frozenset({RunStatus.PUBLISHED, RunStatus.FAILED_RETRYABLE, RunStatus.FAILED_PERMANENT}),
    RunStatus.FAILED_RETRYABLE: frozenset({RunStatus.QUEUED, RunStatus.CANCELLED}),
    RunStatus.FAILED_PROVIDER: frozenset({RunStatus.QUEUED, RunStatus.CANCELLED}),
    RunStatus.FAILED_QC: frozenset({RunStatus.ASSET_GENERATION, RunStatus.SCRIPTING, RunStatus.CANCELLED}),
}


def transition_run(current: RunStatus, target: RunStatus) -> RunStatus:
    if target not in _RUN_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(f"Run cannot transition from {current} to {target}")
    return target


def transition_stage(current: StageStatus, target: StageStatus) -> StageStatus:
    allowed = {
        StageStatus.PENDING: {StageStatus.RUNNING, StageStatus.CANCELLED},
        StageStatus.RUNNING: {StageStatus.SUCCESS, StageStatus.RETRY_WAIT, StageStatus.FAILED_PERMANENT, StageStatus.CANCELLED},
        StageStatus.RETRY_WAIT: {StageStatus.RUNNING, StageStatus.CANCELLED},
    }
    if target not in allowed.get(current, set()):
        raise InvalidTransition(f"Stage cannot transition from {current} to {target}")
    return target


def transition_approval(current: ApprovalStatus, target: ApprovalStatus) -> ApprovalStatus:
    allowed = {
        ApprovalStatus.PENDING: {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.REGENERATE, ApprovalStatus.EDIT_REQUESTED, ApprovalStatus.EXPIRED},
        ApprovalStatus.EDIT_REQUESTED: {ApprovalStatus.PENDING},
    }
    if target not in allowed.get(current, set()):
        raise InvalidTransition(f"Approval cannot transition from {current} to {target}")
    return target


def transition_publication(current: PublicationStatus, target: PublicationStatus) -> PublicationStatus:
    allowed = {
        PublicationStatus.PENDING: {PublicationStatus.QUEUED, PublicationStatus.FAILED_PERMANENT},
        PublicationStatus.QUEUED: {PublicationStatus.UPLOADING, PublicationStatus.FAILED_RETRYABLE, PublicationStatus.FAILED_PERMANENT},
        PublicationStatus.UPLOADING: {PublicationStatus.PUBLISHED, PublicationStatus.FAILED_RETRYABLE, PublicationStatus.FAILED_PERMANENT},
        PublicationStatus.FAILED_RETRYABLE: {PublicationStatus.QUEUED, PublicationStatus.FAILED_PERMANENT},
    }
    if target not in allowed.get(current, set()):
        raise InvalidTransition(f"Publication cannot transition from {current} to {target}")
    return target


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    cooldown_seconds: int = 60
    failures: int = 0
    status: ProviderHealthStatus = ProviderHealthStatus.HEALTHY
    opened_at: datetime | None = None

    def record_success(self) -> None:
        self.failures = 0
        self.status = ProviderHealthStatus.HEALTHY
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.status = ProviderHealthStatus.OPEN
            self.opened_at = _utcnow()
        elif self.status == ProviderHealthStatus.HEALTHY:
            self.status = ProviderHealthStatus.DEGRADED

    def can_probe(self, now: datetime | None = None) -> bool:
        if self.status != ProviderHealthStatus.OPEN or self.opened_at is None:
            return self.status != ProviderHealthStatus.DISABLED
        current = now or _utcnow()
        return (current - self.opened_at).total_seconds() >= self.cooldown_seconds

    def start_probe(self) -> None:
        if not self.can_probe():
            raise InvalidTransition("Circuit breaker is not ready for a half-open probe")
        self.status = ProviderHealthStatus.COOLDOWN
