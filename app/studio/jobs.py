"""The render job shared by local mode (bot subprocess) and GitHub Actions."""

from __future__ import annotations

import base64
import gzip
import json
import time
from pathlib import Path

import httpx

from app.config.settings import Settings
from app.studio.align import build_aligner
from app.studio.factory import build_tts, build_youtube
from app.studio.models import Project, ProjectStatus, ProjectStore
from app.studio.render.pipeline import render_project
from app.studio.telegram import StudioTelegram, keyboard


def encode_payload(project: Project) -> str:
    return base64.b64encode(gzip.compress(project.to_json().encode("utf-8"))).decode("ascii")


def decode_payload(payload: str) -> Project:
    return Project.from_json(gzip.decompress(base64.b64decode(payload)).decode("utf-8"))


def with_attribution(project: Project) -> str:
    credits = sorted({v.attribution for v in project.visuals if v.attribution})
    if not credits:
        return project.description
    return project.description.rstrip() + "\n\nGörseller (Wikimedia Commons): " + "; ".join(credits)


def review_keyboard(project: Project) -> dict[str, object]:
    vid = project.youtube_id or "-"
    return keyboard(
        [("🚀 Yayınla", f"pub:{project.id}:{vid}")],
        [("🔁 Yeniden render", f"rr:{project.id}"), ("🗑 İptal", f"del:{project.id}:{vid}")],
    )


async def run_render_job(
    project: Project,
    settings: Settings,
    *,
    upload: bool = True,
    notify: bool = True,
    tts_override: str = "",
    width: int = 1080,
) -> Project:
    store = ProjectStore(Path(settings.studio_dir))
    bot = StudioTelegram(settings.telegram_bot_token) if settings.telegram_bot_token else None
    chat = project.chat_id or settings.telegram_admin_chat_id
    status_msg: dict[str, object] | None = None
    started = time.time()

    async def progress(msg: str) -> None:
        nonlocal status_msg
        if not (notify and bot and chat):
            print(msg, flush=True)
            return
        text = f"⏳ {project.title or project.topic}\n{msg}  ({int(time.time() - started)} sn)"
        try:
            if status_msg is None:
                status_msg = await bot.send_message(chat, text)
            else:
                await bot.edit_message(chat, int(str(status_msg["message_id"])), text)
        except (httpx.HTTPError, RuntimeError):
            pass

    project.status = ProjectStatus.RENDERING
    store.save(project)
    try:
        out = await render_project(
            project,
            store.workdir(project.id),
            build_tts(settings, tts_override),
            telegram=(lambda fid, dest: bot.download_file(fid, dest)) if bot else None,
            width=width,
            height=width * 16 // 9,
            workers=settings.studio_render_workers or None,
            progress=progress,
            aligner=build_aligner(settings.studio_align_model),
        )
        warnings: list[str] = []
        yt = build_youtube(settings) if upload else None
        if yt is not None:
            await progress("📤 YouTube'a gizli olarak yükleniyor")
            original = project.description
            project.description = with_attribution(project)
            res = await yt.upload_private(project, out.video, out.thumb_vertical)
            project.description = original
            project.youtube_id = res.video_id
            warnings += res.warnings
        elif upload:
            warnings.append("YouTube bilgileri yok: video yüklenmedi, sadece önizleme.")
        project.status = ProjectStatus.REVIEW
        project.error = ""
        store.save(project)
        if notify and bot and chat:
            caption = (
                f"🎬 {project.title}\n⏱ {out.duration:.1f} sn · 🎙 {out.tts_used} · 🔤 {out.alignment}\n"
                + (
                    f"🔒 Gizli yüklendi: https://youtu.be/{project.youtube_id}\n"
                    if project.youtube_id
                    else ""
                )
                + "".join(f"⚠️ {w}\n" for w in warnings)
                + "\nYayınla'ya basınca herkese açık olur."
            )
            await bot.send_file(
                chat,
                out.preview,
                caption,
                method="sendVideo",
                field="video",
                mime="video/mp4",
                reply_markup=review_keyboard(project),
            )
            await bot.send_file(chat, out.thumb_vertical, "Thumbnail (dikey)")
            await bot.send_file(chat, out.thumb_horizontal, "Thumbnail (yatay)")
            meta = (
                f"📝 BAŞLIK\n{project.title}\n\n📄 AÇIKLAMA\n{with_attribution(project)}\n\n"
                f"🏷 ETİKETLER\n{', '.join(project.tags)}\n\n💬 YORUM\n{project.pinned_comment}"
            )
            await bot.send_long(chat, meta)
        return project
    except Exception as exc:  # report every failure back to the admin
        project.status = ProjectStatus.FAILED
        project.error = f"{type(exc).__name__}: {exc}"[:500]
        store.save(project)
        if notify and bot and chat:
            await bot.send_message(
                chat,
                f"❌ Render başarısız: {project.error}",
                keyboard([("🔁 Tekrar dene", f"render:{project.id}")]),
            )
        raise


async def dispatch_github(project: Project, settings: Settings) -> None:
    if not (settings.studio_github_repo and settings.studio_github_token):
        raise RuntimeError("STUDIO_GITHUB_REPO ve STUDIO_GITHUB_TOKEN gerekli")
    payload = encode_payload(project)
    if len(payload) > 60000:
        raise RuntimeError("Proje workflow girdisi için çok büyük")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"https://api.github.com/repos/{settings.studio_github_repo}/actions/workflows/"
            f"{settings.studio_github_workflow}/dispatches",
            headers={
                "Authorization": f"Bearer {settings.studio_github_token}",
                "Accept": "application/vnd.github+json",
            },
            json={"ref": settings.studio_github_ref, "inputs": {"project": payload}},
        )
    if r.status_code != 204:
        raise RuntimeError(f"GitHub dispatch HTTP {r.status_code}: {r.text[:200]}")


def write_project_file(project: Project, path: Path) -> Path:
    path.write_text(json.dumps(project.to_dict(), ensure_ascii=False), encoding="utf-8")
    return path
