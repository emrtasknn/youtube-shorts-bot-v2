"""Telegram helpers Studio needs on top of the existing TelegramBot client."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx

from app.infrastructure.telegram.bot import TelegramBot


def keyboard(*rows: list[tuple[str, str]]) -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


class StudioTelegram(TelegramBot):
    async def send_long(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> None:
        """Telegram caps messages at 4096 chars; split on line breaks."""
        chunks: list[str] = []
        cur = ""
        for line in text.splitlines(keepends=True):
            if len(cur) + len(line) > 3800:
                chunks.append(cur)
                cur = ""
            cur += line
        if cur:
            chunks.append(cur)
        for i, chunk in enumerate(chunks):
            await self.send_message(chat_id, chunk, reply_markup if i == len(chunks) - 1 else None)

    async def send_photo_url(
        self,
        chat_id: int,
        url: str,
        caption: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "photo": url, "caption": caption[:1000]}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self._call("sendPhoto", json=payload)

    async def send_file(
        self,
        chat_id: int,
        path: Path,
        caption: str = "",
        *,
        method: str = "sendDocument",
        field: str = "document",
        mime: str = "application/octet-stream",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"chat_id": str(chat_id), "caption": caption[:1000]}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        with path.open("rb") as fh:
            async with httpx.AsyncClient(timeout=max(self._timeout, 300.0)) as client:
                r = await client.post(
                    f"{self._base_url}/{method}",
                    data=data,
                    files={field: (path.name, fh, mime)},
                )
        r.raise_for_status()
        payload = r.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {payload}")
        return cast(dict[str, Any], payload["result"])

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        try:
            await self._call("sendChatAction", json={"chat_id": chat_id, "action": action})
        except (httpx.HTTPError, RuntimeError):
            pass
