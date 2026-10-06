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
