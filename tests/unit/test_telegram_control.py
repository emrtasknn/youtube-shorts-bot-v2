from pathlib import Path
from uuid import uuid4

import pytest

from app.domain.enums import ApprovalStatus, RunStatus
from app.domain.state_machine import InvalidTransition, transition_approval, transition_run


def test_approval_transitions_are_terminal_after_resolution() -> None:
    assert (
        transition_approval(ApprovalStatus.PENDING, ApprovalStatus.APPROVED)
        == ApprovalStatus.APPROVED
    )
    with pytest.raises(InvalidTransition):
        transition_approval(ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)


def test_run_approval_and_publish_transitions() -> None:
    assert (
        transition_run(RunStatus.READY_FOR_APPROVAL, RunStatus.APPROVED)
        == RunStatus.APPROVED
    )
    assert (
        transition_run(RunStatus.APPROVED, RunStatus.PUBLISHING)
        == RunStatus.PUBLISHING
    )
    assert (
        transition_run(RunStatus.PUBLISHING, RunStatus.PUBLISHED)
        == RunStatus.PUBLISHED
    )


def test_run_cannot_publish_before_approval() -> None:
    with pytest.raises(InvalidTransition):
        transition_run(RunStatus.READY_FOR_APPROVAL, RunStatus.PUBLISHING)


def test_video_path_shape_is_run_scoped() -> None:
    run_id = uuid4()
    path = Path("storage/runs") / str(run_id) / "voiceover.mp3"
    assert path.parent.name == str(run_id)
