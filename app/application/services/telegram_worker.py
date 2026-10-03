from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.telegram_control import TelegramControlPlane
from app.infrastructure.database.models import ApprovalModel, RunModel
from app.infrastructure.telegram.bot import TelegramBot


class TelegramWorker:
    def __init__(
        self,
        session: Session,
        bot: TelegramBot,
        control: TelegramControlPlane,
        admin_chat_id: int,
        admin_user_id: int,
    ) -> None:
        self._session = session
        self._bot = bot
        self._control = control
        self._admin_chat_id = admin_chat_id
        self._admin_user_id = admin_user_id
        self._offset: int | None = None

    async def send_pending(self) -> int:
        approvals = self._session.scalars(
            select(ApprovalModel).where(ApprovalModel.status == "PENDING")
        ).all()
        sent = 0
        for approval in approvals:
            run = self._session.get(RunModel, approval.run_id)
            if run and run.status.value == "READY_FOR_APPROVAL":
                await self._control.send_review(self._admin_chat_id, run.id)
                sent += 1
        return sent

    async def run_forever(self) -> None:
        while True:
            try:
                updates = await self._bot.get_updates(offset=self._offset, timeout=25)
                for update in updates:
                    self._offset = int(update["update_id"]) + 1
                    await self._handle(update)
            except Exception as exc:
                await asyncio.sleep(3)
                await self._bot.send_message(self._admin_chat_id, f"Telegram worker error: {exc}")

    async def _handle(self, update: dict[str, object]) -> None:
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            user = callback.get("from") or {}
            if not isinstance(user, dict) or int(user.get("id", -1)) != self._admin_user_id:
                await self._bot.answer_callback(str(callback.get("id")), "Unauthorized")
                return
            data = str(callback.get("data") or "")
            try:
                action, raw_run_id = data.split(":", 1)
                run_id = UUID(raw_run_id)
                raw_username = user.get("username")
                username = raw_username if isinstance(raw_username, str) else str(user.get("id"))
                if action == "approve":
                    message = await self._control.approve(run_id, username)
                    await self._bot.answer_callback(str(callback["id"]), message)
                    await self._bot.send_message(
                        self._admin_chat_id,
                        message,
                        self._control._keyboard(run_id, approved=True),
                    )
                elif action == "reject":
                    message = await self._control.reject(run_id, username)
                    await self._bot.answer_callback(str(callback["id"]), message)
                elif action == "regenerate":
                    message = await self._control.regenerate(run_id, username)
                    await self._bot.answer_callback(str(callback["id"]), "Regeneration started")
                    await self._bot.send_message(self._admin_chat_id, message)
                elif action == "publish":
                    message = await self._control.publish(run_id, username)
                    await self._bot.answer_callback(
                        str(callback["id"]),
                        "Published" if message.startswith("Published") else message,
                    )
                    await self._bot.send_message(self._admin_chat_id, message)
                else:
                    await self._bot.answer_callback(str(callback["id"]), "Unknown action")
            except Exception as exc:
                await self._bot.answer_callback(str(callback.get("id")), "Action failed")
                await self._bot.send_message(self._admin_chat_id, f"M5 action failed: {exc}")
            return
        update_message = update.get("message")
        if isinstance(update_message, dict) and str(update_message.get("text", "")).strip() == "/review":
            chat = update_message.get("chat") or {}
            if isinstance(chat, dict) and int(chat.get("id", -1)) == self._admin_chat_id:
                await self.send_pending()
