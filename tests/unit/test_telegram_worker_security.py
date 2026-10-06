from __future__ import annotations

import pytest

from app.application.services.telegram_worker import TelegramWorker


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.answers: list[str] = []

    async def answer_callback(self, callback_id: str, text: str) -> None:
        self.answers.append(text)

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, object] | None = None
    ) -> None:
        self.messages.append(text)


class FailingControl:
    async def approve(self, run_id, user):
        raise RuntimeError("secret-token=should-never-leak")


@pytest.mark.asyncio
async def test_telegram_action_error_does_not_expose_exception() -> None:
    bot = FakeBot()
    worker = TelegramWorker(
        session=None,  # type: ignore[arg-type]
        bot=bot,  # type: ignore[arg-type]
        control=FailingControl(),  # type: ignore[arg-type]
        admin_chat_id=1,
        admin_user_id=42,
    )

    await worker._handle(
        {
            "callback_query": {
                "id": "callback-1",
                "from": {"id": 42, "username": "admin"},
                "data": "approve:00000000-0000-0000-0000-000000000001",
            }
        }
    )

    assert bot.answers == ["Action failed"]
    assert bot.messages == ["Telegram action failed. Check application logs for details."]
    assert "secret-token" not in bot.messages[0]


class FakeApproval:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id


class FakeRun:
    def __init__(self, run_id: str) -> None:
        self.id = run_id
        self.status = "READY_FOR_APPROVAL"


class FakeScalarResult:
    def __init__(self, approvals: list[FakeApproval]) -> None:
        self._approvals = approvals

    def all(self) -> list[FakeApproval]:
        return self._approvals


class ReviewSession:
    def __init__(self, approvals: list[FakeApproval], runs: dict[str, FakeRun]) -> None:
        self._approvals = approvals
        self._runs = runs

    def scalars(self, _query):
        return FakeScalarResult(self._approvals)

    def get(self, _model, run_id: str):
        return self._runs.get(run_id)


class PartiallyFailingControl:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_review(self, _chat_id: int, run_id: str) -> None:
        if run_id == "stale":
            raise FileNotFoundError("stale generated video")
        self.sent.append(run_id)


@pytest.mark.asyncio
async def test_send_pending_does_not_block_new_ready_run_on_stale_media() -> None:
    approvals = [FakeApproval("stale"), FakeApproval("current")]
    runs = {"stale": FakeRun("stale"), "current": FakeRun("current")}
    session = ReviewSession(approvals, runs)
    control = PartiallyFailingControl()
    worker = TelegramWorker(
        session=session,  # type: ignore[arg-type]
        bot=FakeBot(),  # type: ignore[arg-type]
        control=control,  # type: ignore[arg-type]
        admin_chat_id=1,
        admin_user_id=42,
    )

    sent = await worker.send_pending()

    assert sent == 1
    assert control.sent == ["current"]
