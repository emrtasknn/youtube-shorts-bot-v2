from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx


class TelegramBot:
    def __init__(self, token: str, *, timeout_seconds: float = 60.0) -> None:
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._timeout = timeout_seconds

    async def _call(self, method: str, **kwargs: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self._base_url}/{method}", **kwargs)
            response.raise_for_status()
            payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {payload}")
        return cast(dict[str, Any], payload["result"])

    async def get_updates(
        self, *, offset: int | None = None, timeout: int = 25
    ) -> list[dict[str, Any]]:
        result = await self._call(
            "getUpdates",
            json={
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        return cast(list[dict[str, Any]], result)

    async def set_webhook(self, url: str, *, secret_token: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {"url": url, "allowed_updates": ["message", "callback_query"]}
        if secret_token:
            payload["secret_token"] = secret_token
        return await self._call("setWebhook", json=payload)

    async def delete_webhook(self) -> dict[str, Any]:
        return await self._call("deleteWebhook", json={})

    async def answer_callback(self, callback_query_id: str, text: str) -> None:
        await self._call(
            "answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
        )

    async def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self._call("sendMessage", json=payload)

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._call("editMessageText", json=payload)

    async def get_file(self, file_id: str) -> dict[str, Any]:
        return await self._call("getFile", json={"file_id": file_id})

    async def download_file(self, file_id: str, destination: Path) -> Path:
        file_info = await self.get_file(file_id)
        file_path = str(file_info.get("file_path") or "")
        if not file_path:
            raise RuntimeError(f"Telegram getFile returned no file_path for {file_id}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=max(self._timeout, 180.0)) as client:
            response = await client.get(
                f"{self._base_url.replace('/bot', '/file/bot')}/{file_path}"
            )
            response.raise_for_status()
            destination.write_bytes(response.content)
        return destination

    async def send_video(
        self,
        chat_id: int,
        video_path: Path,
        caption: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"chat_id": str(chat_id), "caption": caption}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        with video_path.open("rb") as video:
            files = {"video": (video_path.name, video, "video/mp4")}
            async with httpx.AsyncClient(timeout=max(self._timeout, 180.0)) as client:
                response = await client.post(
                    f"{self._base_url}/sendVideo",
                    data=data,
                    files=files,
                )
                response.raise_for_status()
                payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram sendVideo failed: {payload}")
        return cast(dict[str, Any], payload["result"])
