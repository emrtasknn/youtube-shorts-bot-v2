from pathlib import Path
from typing import Any

import pytest

from app.config.settings import Settings
from app.infrastructure.providers.youtube import YouTubePublishError
from app.studio import jobs
from app.studio.models import Line, Project, ProjectStatus, Visual
from app.studio.render.pipeline import RenderOutput


class FakeBot:
    def __init__(self, token: str) -> None:
        self.files: list[tuple[str, str, Any]] = []
        self.messages: list[str] = []

    async def send_message(self, chat: int, text: str, reply_markup: Any = None) -> dict[str, Any]:
        self.messages.append(text)
        return {"message_id": 1}

    async def edit_message(self, chat: int, message_id: int, text: str) -> None:
        self.messages.append(text)

    async def send_file(
        self, chat: int, path: Path, caption: str = "", **kw: Any
    ) -> dict[str, Any]:
        self.files.append((path.name, caption, kw.get("reply_markup")))
        return {}

    async def send_long(self, chat: int, text: str, reply_markup: Any = None) -> None:
        self.messages.append(text)


@pytest.mark.asyncio
async def test_preview_is_sent_even_when_youtube_upload_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bots: list[FakeBot] = []

    def make_bot(token: str) -> FakeBot:
        bots.append(FakeBot(token))
        return bots[-1]

    async def fake_render(project: Project, workdir: Path, tts: Any, **kw: Any) -> RenderOutput:
        files = {}
        for name in ("final.mp4", "preview.mp4", "thumb_vertical.jpg", "thumb_horizontal.jpg"):
            files[name] = workdir / name
            files[name].write_bytes(b"x")
        return RenderOutput(
            video=files["final.mp4"],
            preview=files["preview.mp4"],
            thumb_vertical=files["thumb_vertical.jpg"],
            thumb_horizontal=files["thumb_horizontal.jpg"],
            duration=42.0,
            tts_used="ema",
            alignment="ema (100%)",
        )

    class BrokenYouTube:
        async def check(self) -> str:
            return "Kanal"

        async def upload_private(self, *a: Any) -> Any:
            raise YouTubePublishError(
                "YouTube OAuth token yenilenemedi: invalid_grant", retryable=False
            )

    monkeypatch.setattr(jobs, "StudioTelegram", make_bot)
    monkeypatch.setattr(jobs, "render_project", fake_render)
    monkeypatch.setattr(jobs, "build_youtube", lambda s: BrokenYouTube())
    monkeypatch.setattr(jobs, "build_tts", lambda s, o="": object())
    monkeypatch.setattr(jobs, "build_aligner", lambda m: None)

    project = Project(
        topic="Emu", title="Emu", lines=[Line("Emular kazandı.")], visuals=[Visual("e")]
    )
    project.chat_id = 5
    settings = Settings(telegram_bot_token="1:x", studio_dir=str(tmp_path))
    done = await jobs.run_render_job(project, settings)

    assert done.status == ProjectStatus.REVIEW and done.youtube_id == ""
    caption = bots[0].files[0][1]
    assert bots[0].files[0][0] == "preview.mp4"
    assert "YouTube'a yüklenemedi: YouTube OAuth token yenilenemedi: invalid_grant" in caption
    assert "Yeniden render" in caption and "Yayınla'ya basınca" not in caption
    assert done.description == project.description  # attribution not left behind


@pytest.mark.asyncio
async def test_bad_token_is_reported_before_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bots: list[FakeBot] = []
    order: list[str] = []

    def make_bot(token: str) -> FakeBot:
        bots.append(FakeBot(token))
        return bots[-1]

    async def fake_render(project: Project, workdir: Path, tts: Any, **kw: Any) -> RenderOutput:
        order.append("render")
        names = ("final.mp4", "preview.mp4", "thumb_vertical.jpg", "thumb_horizontal.jpg")
        paths = [workdir / n for n in names]
        for path in paths:
            path.write_bytes(b"x")
        return RenderOutput(*paths, duration=40.0, tts_used="ema")  # type: ignore[call-arg]

    class BadToken:
        async def check(self) -> str:
            order.append("check")
            raise YouTubePublishError(
                "YouTube OAuth token yenilenemedi: invalid_grant", retryable=False
            )

        async def upload_private(self, *a: Any) -> Any:
            raise AssertionError("must not upload with a bad token")

    monkeypatch.setattr(jobs, "StudioTelegram", make_bot)
    monkeypatch.setattr(jobs, "render_project", fake_render)
    monkeypatch.setattr(jobs, "build_youtube", lambda s: BadToken())
    monkeypatch.setattr(jobs, "build_tts", lambda s, o="": object())
    monkeypatch.setattr(jobs, "build_aligner", lambda m: None)

    project = Project(
        topic="Emu", title="Emu", lines=[Line("Emular kazandı.")], visuals=[Visual("e")]
    )
    project.chat_id = 5
    done = await jobs.run_render_job(
        project, Settings(telegram_bot_token="1:x", studio_dir=str(tmp_path))
    )
    assert order == ["check", "render"]
    assert any("token hatalı" in m and "invalid_grant" in m for m in bots[0].messages)
    caption = bots[0].files[0][1]
    assert "invalid_grant" in caption and done.youtube_id == ""
    assert "plan:" not in str(bots[0].files[0][2])  # no Planla without an upload
