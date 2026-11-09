"""Studio Telegram bot: topic -> script approval -> visuals -> render -> publish.

Commands
  /yeni <konu>          new Short (a long pasted text works too: line 1 = topic)
  /metin                show the script again
  /gorseller            list visuals and which are still missing
  /render               render now
  /durum                current project status
  /iptal                cancel current project
Editing (plain messages)
  5: yeni cümle         replace line 5 (shown caption + narration)
  5 -> 3                line 5 uses visual 3
  g3: açıklama          change visual 3 description / search hint
  düzelt: daha kısa     ask the writer to revise the whole script
Visuals
  send photos in order, or put the visual number in the photo caption ("3").
Your own photos with the topic
  send photos first (caption = what it shows), then /yeni <konu>: the script is
  built around them. Or send one album with the caption "/yeni <konu>".
  /havuz                show the waiting photos · /havuz temizle to empty it
  caption "+" or "havuz" adds a photo to the pool while a project is open.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import datetime
from typing import Any

import httpx

from app.config.settings import Settings
from app.infrastructure.providers.youtube import YouTubePublishError
from app.studio import schedule
from app.studio.factory import build_llm, build_store, build_youtube
from app.studio.jobs import dispatch_github, write_project_file
from app.studio.llm import LLMError
from app.studio.models import Project, ProjectStatus, UserPhoto
from app.studio.script_writer import (
    ScriptWriter,
    project_from_script,
    split_topic_and_notes,
    user_photos_of,
)
from app.studio.telegram import StudioTelegram, keyboard
from app.studio.text import spell_numbers
from app.studio.visual_search import image_url, search_commons_terms, search_terms

log = logging.getLogger("studio.bot")

HELP = """🎬 Bir Garip Tarih · Shorts Stüdyosu

Akış: konu → metin onayı → görseller → render → yayın

📌 KOMUTLAR
/yeni <konu> · yapay zekâ metni yazsın
/senaryo · kendi metnini yapıştır (yapay zekâ kullanmaz)
   ilk satır: /senaryo Başlık, alt satırlar: metin. Her cümle bir sahne olur.
/metin · metni tekrar göster
/gorseller · görselleri ve eksikleri göster
/render · videoyu hazırla
/durum · projenin durumu
/iptal · projeyi iptal et
/havuz · bekleyen fotoğrafları göster
/havuz temizle · havuzu boşalt
/youtube · YouTube bağlantısını test et

⏰ PLANLI YAYIN
Önizlemedeki ⏰ Planla düğmesi ya da: plan yarın 18:30 · plan 12.11 21:00
YouTube videoyu o saatte kendisi herkese açar.

✏️ METNİ DÜZENLEME (düz mesaj olarak yaz)
5: yeni cümle → 5. satırı değiştirir
5 -> 3 → 5. satır 3. görseli kullanır
g3: açıklama → 3. görselin tarifini değiştirir
g3: https://… → 3. görsel bu linkteki resim olur (Commons sayfa linki de olur)
düzelt: daha kısa yap → metni baştan yazdırır

🖼 GÖRSELLER
• Metni onayladıktan sonra fotoğrafları sırayla gönder.
• Belirli bir görsele koymak için açıklamaya numarasını yaz: 3
• Eksikler için 🔎 düğmesiyle Wikimedia'dan aday seçebilirsin.

📥 KENDİ FOTOĞRAFLARINLA BAŞLA
• Önce fotoğrafları gönder, açıklamaya içinde ne olduğunu yaz.
  Sonra /yeni <konu> yaz: metin bu fotoğrafların etrafında kurulur.
• Ya da tek bir albüm gönder, albümün açıklaması: /yeni <konu>
• Proje açıkken açıklamaya "+" yazarsan fotoğraf bir sonraki video
  için havuza gider."""
LINE_EDIT = re.compile(r"^\s*(\d{1,2})\s*[:.)-]\s*(.+)$", re.S)
LINE_VISUAL = re.compile(r"^\s*(\d{1,2})\s*->\s*(\d{1,2})\s*$")
VISUAL_EDIT = re.compile(r"^\s*g(\d{1,2})\s*:\s*(.+)$", re.I | re.S)
REVISE = re.compile(r"^\s*(düzelt|duzelt|revize)\s*:\s*(.+)$", re.I | re.S)
PLAN = re.compile(r"^\s*plan(?:la)?(?:\s*:\s*|\s+)(\S.*)$", re.I)
TO_POOL = re.compile(r"^\s*(\+|havuz\b)\s*", re.I)
ALBUM_WAIT = 2.5  # seconds to wait for the rest of an album before writing the script
OPEN = (ProjectStatus.DRAFT, ProjectStatus.COLLECTING)


def short_llm_error(exc: Exception) -> str:
    """One short line per provider instead of raw JSON error bodies."""
    parts = []
    for part in str(exc).split(" | "):
        name, _, detail = part.partition(":")
        low = detail.lower()
        if "api key not valid" in low or "api_key_invalid" in low or "invalid api key" in low:
            detail = " API anahtarı geçersiz"
        elif "json_validate_failed" in low or "json" in low and "valid" in low:
            detail = " geçerli JSON üretemedi"
        elif "429" in low or "rate" in low and "limit" in low:
            detail = " istek sınırı doldu, biraz sonra dene"
        elif m := re.search(r'"message"\s*:\s*"([^"]+)', detail):
            detail = " " + m.group(1)[:140]
        else:
            detail = detail[:140]
        parts.append(f"• {name.replace('LLM', '')}:{detail}")
    return "\n".join(parts)


def render_script(p: Project) -> str:
    out = [f"🎬 {p.title}", f"🖼 Kapak yazısı: {p.thumbnail_text}", "", "📜 METİN"]
    last_kicker = ""
    for i, ln in enumerate(p.lines, 1):
        if ln.kicker and ln.kicker != last_kicker:
            out.append(f"   ▸ {ln.kicker}")
            last_kicker = ln.kicker
        tag = f"💥 KART «{ln.card}»" if ln.card else f"[g{ln.visual + 1}]"
        out.append(f"{i}. {tag} {ln.shown}")
    out += ["", "🖼 GÖRSELLER"]
    for i, v in enumerate(p.visuals, 1):
        mark = "✅" if v.filled else "▫️"
        out.append(f"g{i} {mark} {v.description}")
    out += [
        "",
        "Düzenleme: `5: yeni cümle` · `5 -> 3` · `g3: açıklama` · `düzelt: istek`",
    ]
    return "\n".join(out)


def visuals_status(p: Project) -> str:
    missing = p.missing_visuals()
    lines = [
        f"🖼 Görseller ({len(p.visuals) - len([v for v in p.visuals if not v.filled])}"
        f"/{len(p.visuals)} hazır)"
    ]
    for i, v in enumerate(p.visuals, 1):
        lines.append(f"{'✅' if v.filled else '▫️'} {i}. {v.description}")
    if missing:
        lines.append("")
        lines.append(
            "Fotoğrafları sırayla gönder (ya da fotoğraf açıklamasına numara yaz). "
            "Eksikler için 🔎 Bul'a bas."
        )
    else:
        lines.append("\nHepsi hazır 🎉")
    return "\n".join(lines)


class StudioBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bot = StudioTelegram(settings.telegram_bot_token)
        self.store = build_store(settings)
        self._writer: ScriptWriter | None = None
        self._jobs: set[asyncio.Task[None]] = set()
        self._pool_albums: set[str] = set()  # media_group_ids whose photos go to the pool
        self._acked_albums: set[str] = set()

    @property
    def writer(self) -> ScriptWriter:
        if self._writer is None:
            self._writer = ScriptWriter(build_llm(self.settings))
        return self._writer

    # ------------------------------------------------------------ plumbing
    def _authorized(self, user_id: int) -> bool:
        admin = self.settings.telegram_admin_user_id
        return not admin or user_id == admin

    async def run(self) -> None:
        offset: int | None = None
        try:
            await self.bot.delete_webhook()
        except (httpx.HTTPError, RuntimeError):
            pass
        log.info("Studio bot polling")
        while True:
            try:
                updates = await self.bot.get_updates(offset=offset, timeout=25)
            except (httpx.HTTPError, RuntimeError) as exc:
                log.warning("getUpdates failed: %s", exc)
                await asyncio.sleep(5)
                continue
            for upd in updates:
                offset = int(upd["update_id"]) + 1
                try:
                    await self.handle(upd)
                except Exception:
                    log.exception("update failed")

    async def handle(self, upd: dict[str, Any]) -> None:
        if "callback_query" in upd:
            cq = upd["callback_query"]
            if not self._authorized(int(cq["from"]["id"])):
                return
            await self.bot.answer_callback(str(cq["id"]), "👍")
            await self.on_callback(int(cq["message"]["chat"]["id"]), str(cq.get("data", "")))
            return
        msg = upd.get("message")
        if not msg or not self._authorized(int(msg.get("from", {}).get("id", 0))):
            return
        chat = int(msg["chat"]["id"])
        if "photo" in msg or (
            "document" in msg and str(msg["document"].get("mime_type", "")).startswith("image/")
        ):
            await self.on_photo(chat, msg)
            return
        text = str(msg.get("text", "")).strip()
        if text:
            await self.on_text(chat, text)

    async def say(self, chat: int, text: str, markup: dict[str, Any] | None = None) -> None:
        await self.bot.send_long(chat, text, markup)

    def current(self, chat: int) -> Project | None:
        return self.store.latest_for_chat(chat)

    # ------------------------------------------------------------ text
    async def on_text(self, chat: int, text: str) -> None:
        head, *rest = re.split(r"\s", text, maxsplit=1)
        cmd, arg = head.split("@")[0].lower(), (rest[0] if rest else "")
        if cmd in ("/start", "/yardim", "/help"):
            await self.say(chat, HELP)
            return
        if cmd == "/yeni":
            if not arg.strip():
                await self.say(
                    chat, "Kullanım: /yeni Röntgen'in keşfi  (uzun metin de yapıştırabilirsin)"
                )
                return
            await self.new_project(chat, arg)
            return
        if cmd == "/youtube":
            await self.check_youtube(chat)
            return
        if cmd == "/senaryo":
            await self.new_project_from_script(chat, arg)
            return
        if cmd == "/havuz":
            await self.show_pool(chat, clear=arg.strip().lower() in ("temizle", "sil", "boşalt"))
            return
        p = self.current(chat)
        if p is None:
            await self.say(chat, "Aktif proje yok. /yeni <konu> ile başla.")
            return
        if cmd == "/metin":
            await self.send_script(chat, p)
        elif cmd == "/gorseller":
            await self.say(chat, visuals_status(p), self._visual_buttons(p))
        elif cmd == "/render":
            await self.start_render(chat, p)
        elif cmd == "/durum":
            await self.say(chat, f"📌 {p.title or p.topic}\nDurum: {p.status.value}\n{p.error}")
        elif cmd == "/iptal":
            p.status = ProjectStatus.CANCELLED
            self.store.save(p)
            await self.say(chat, "🗑 Proje iptal edildi.")
        else:
            await self.on_edit(chat, p, text)

    async def on_edit(self, chat: int, p: Project, text: str) -> None:
        if m := PLAN.match(text):
            await self.plan_from_text(chat, p, m.group(1))
            return
        if m := REVISE.match(text):
            await self.say(chat, "✍️ Metin yeniden yazılıyor…")
            try:
                revised = await self.writer.revise(p, m.group(2))
            except LLMError as exc:
                await self.say(chat, f"❌ {exc}")
                return
            revised.status = ProjectStatus.DRAFT
            self.store.save(revised)
            await self.send_script(chat, revised)
            return
        if m := LINE_VISUAL.match(text):
            li, vi = int(m.group(1)) - 1, int(m.group(2)) - 1
            if 0 <= li < len(p.lines) and 0 <= vi < len(p.visuals):
                p.lines[li].visual = vi
                p.lines[li].card = ""
                self.store.save(p)
                await self.say(chat, f"✅ {li + 1}. satır artık g{vi + 1} görselini kullanıyor.")
            else:
                await self.say(chat, "Satır ya da görsel numarası geçersiz.")
            return
        if m := VISUAL_EDIT.match(text):
            vi = int(m.group(1)) - 1
            if 0 <= vi < len(p.visuals):
                value = m.group(2).strip()
                v = p.visuals[vi]
                if re.match(r"^https?://\S+$", value):
                    # a link: use that picture directly
                    v.source, v.attribution, v.focus_x, v.focus_y = (
                        f"url:{image_url(value)}",
                        "",
                        None,
                        None,
                    )
                    v.candidates = []
                    if p.status == ProjectStatus.DRAFT:
                        p.status = ProjectStatus.COLLECTING
                    self.store.save(p)
                    missing = p.missing_visuals()
                    tail = (
                        "Eksik: " + ", ".join(f"g{i + 1}" for i in missing)
                        if missing
                        else "Tüm görseller hazır! 🎬 Render'a basabilirsin."
                    )
                    await self.say(chat, f"✅ g{vi + 1} linkten kaydedildi.\n{tail}")
                    return
                v.description, v.query, v.candidates = value, "", []
                self.store.save(p)
                await self.say(chat, f"✅ g{vi + 1}: {v.description}")
            return
        if m := LINE_EDIT.match(text):
            li = int(m.group(1)) - 1
            if 0 <= li < len(p.lines):
                new = m.group(2).strip()
                p.lines[li].caption = new
                p.lines[li].narration = spell_numbers(new)
                self.store.save(p)
                await self.say(chat, f"✅ {li + 1}. satır güncellendi:\n{new}")
            else:
                await self.say(chat, "Bu numarada satır yok.")
            return
        await self.say(chat, "Anlamadım 🙃 /yardim yazarak komutları görebilirsin.")

    # ------------------------------------------------------------ flow steps
    async def new_project(self, chat: int, message: str) -> None:
        topic, notes = split_topic_and_notes(message)
        photos = self.store.inbox(chat)
        await self.bot.send_chat_action(chat)
        extra = f" (📎 {len(photos)} fotoğrafın kullanılacak)" if photos else ""
        await self.say(chat, f"✍️ «{topic}» için metin yazılıyor…{extra}")
        try:
            p = await self.writer.write(topic, notes, photos)
        except LLMError as exc:
            await self.say(
                chat,
                f"❌ Metin yazılamadı:\n{short_llm_error(exc)}\n\n"
                "Kendi metninle devam edebilirsin:\n/senaryo Başlık\n(alt satırlara metni yapıştır)",
            )
            return
        self.store.clear_inbox(chat)
        old = self.current(chat)
        if old is not None and old.status in (ProjectStatus.DRAFT, ProjectStatus.COLLECTING):
            old.status = ProjectStatus.CANCELLED
            self.store.save(old)
        p.chat_id = chat
        self.store.save(p)
        if self.writer.provider:
            await self.say(chat, f"🤖 Metni yazan: {self.writer.provider}")
        await self.send_script(chat, p)

    async def new_project_from_script(self, chat: int, message: str) -> None:
        title, _, script = message.strip().partition("\n")
        if not script.strip():
            await self.say(
                chat,
                "Kullanım (tek mesajda):\n/senaryo Emu Savaşı\n1932'de Avustralya ordusu emulara "
                "savaş açtı.\nVe bu savaşı kuşlar kazandı.\n\nİlk satır başlık, alt satırlar "
                "metin. Her cümle bir sahne olur.",
            )
            return
        photos = self.store.inbox(chat)
        try:
            p = project_from_script(title, script, photos)
        except LLMError as exc:
            await self.say(chat, f"❌ {exc}")
            return
        old = self.current(chat)
        if old is not None and old.status in (ProjectStatus.DRAFT, ProjectStatus.COLLECTING):
            old.status = ProjectStatus.CANCELLED
            self.store.save(old)
        p.chat_id = chat
        self.store.save(p)
        self.store.clear_inbox(chat)
        extra = f" · 📎 {len(photos)} fotoğrafın sahnelere dağıtıldı" if photos else ""
        await self.say(chat, f"📝 Senaryodan {len(p.lines)} sahne çıkarıldı{extra}.")
        await self.send_script(chat, p)

    async def send_script(self, chat: int, p: Project) -> None:
        await self.say(
            chat,
            render_script(p),
            keyboard(
                [("✅ Metni onayla", f"ok:{p.id}")],
                [("🔁 Baştan yaz", f"rw:{p.id}")],
            ),
        )

    def _visual_buttons(self, p: Project) -> dict[str, Any]:
        rows = []
        if p.missing_visuals():
            rows.append([("🔎 Eksikleri Wikimedia'da bul", f"find:{p.id}")])
        rows.append([("🎬 Render", f"render:{p.id}")])
        return keyboard(*rows)

    async def show_pool(self, chat: int, *, clear: bool = False) -> None:
        if clear:
            self.store.clear_inbox(chat)
            await self.say(chat, "🧹 Görsel havuzu boşaltıldı.")
            return
        photos = self.store.inbox(chat)
        if not photos:
            await self.say(
                chat,
                "📥 Havuz boş. Fotoğraf gönder (açıklamaya ne olduğunu yaz), sonra /yeni <konu>.",
            )
            return
        rows = [f"{i}. {ph.note or '(açıklamasız)'}" for i, ph in enumerate(photos, 1)]
        await self.say(
            chat,
            f"📥 Havuzda {len(photos)} fotoğraf:\n"
            + "\n".join(rows)
            + "\n\n/yeni <konu> yazınca metin bunlarla kurulacak · /havuz temizle",
        )

    async def _to_pool(self, chat: int, file_id: str, note: str, album: str) -> None:
        n = self.store.add_to_inbox(chat, UserPhoto(f"telegram:{file_id}", note))
        if album:
            if album in self._acked_albums:
                return  # one reply per album is enough
            self._acked_albums.add(album)
        await self.say(
            chat,
            f"📥 Havuza eklendi ({n}). Başka fotoğraf da gönderebilirsin; "
            "/yeni <konu> yazınca metin bu görsellerle kurulacak.",
        )

    async def _start_after_album(self, chat: int, message: str, album: str) -> None:
        if album:
            await asyncio.sleep(ALBUM_WAIT)  # let the album's other photos arrive
        try:
            await self.new_project(chat, message)
        finally:
            self._pool_albums.discard(album)
            self._acked_albums.discard(album)

    async def on_photo(self, chat: int, msg: dict[str, Any]) -> None:
        if "photo" in msg:
            file_id = str(max(msg["photo"], key=lambda ph: int(ph.get("file_size", 0)))["file_id"])
        else:
            file_id = str(msg["document"]["file_id"])
        caption = str(msg.get("caption", "")).strip()
        album = str(msg.get("media_group_id", ""))

        # photo (or album) captioned "/yeni <konu>": pool it and start the project with it
        cmd, _, arg = caption.partition(" ")
        if cmd.split("@")[0].lower() == "/yeni":
            if not arg.strip():
                await self.say(chat, "Açıklamaya konuyu da yaz: /yeni Emu Savaşı")
                return
            self.store.add_to_inbox(chat, UserPhoto(f"telegram:{file_id}"))
            if album:
                self._pool_albums.add(album)
                self._acked_albums.add(album)
            task = asyncio.create_task(self._start_after_album(chat, arg, album))
            self._jobs.add(task)
            task.add_done_callback(self._jobs.discard)
            return
        if album and album in self._pool_albums:
            self.store.add_to_inbox(chat, UserPhoto(f"telegram:{file_id}", caption))
            return
        p = self.current(chat)
        if m := TO_POOL.match(caption):
            await self._to_pool(chat, file_id, caption[m.end() :].strip(), album)
            return
        if p is None or p.status not in OPEN:
            # no open project: keep the picture for the next topic
            if album:
                self._pool_albums.add(album)
            await self._to_pool(chat, file_id, caption, album)
            return
        if p.status == ProjectStatus.DRAFT:
            p.status = ProjectStatus.COLLECTING  # sending photos implies script approval
        target: int | None = None
        if m := re.match(r"^g?(\d{1,2})", caption, re.I):
            target = int(m.group(1)) - 1
            if not 0 <= target < len(p.visuals):
                await self.say(chat, f"Görsel {target + 1} yok (1-{len(p.visuals)}).")
                return
        else:
            target = p.next_empty_visual()
        if target is None:
            await self.say(
                chat, "Tüm görseller dolu. Değiştirmek için açıklamaya numara yaz (örn. 3)."
            )
            return
        v = p.visuals[target]
        v.source, v.attribution, v.focus_x, v.focus_y = f"telegram:{file_id}", "", None, None
        self.store.save(p)
        missing = p.missing_visuals()
        tail = (
            "Eksik: " + ", ".join(f"g{i + 1}" for i in missing)
            if missing
            else "Tüm görseller hazır! 🎬 Render'a basabilirsin."
        )
        await self.say(
            chat,
            f"✅ g{target + 1} kaydedildi — {v.description}\n{tail}",
            self._visual_buttons(p) if not missing else keyboard([("🎬 Render", f"render:{p.id}")]),
        )

    async def find_candidates(self, chat: int, p: Project) -> None:
        missing = p.missing_visuals()
        if not missing:
            await self.say(chat, "Eksik görsel yok.")
            return
        await self.say(chat, f"🔎 {len(missing)} görsel için aday aranıyor…")
        for vi in missing:
            v = p.visuals[vi]
            queries = ([v.query] if v.query else []) + search_terms(v.description)
            try:
                v.candidates = await search_commons_terms(queries)
            except httpx.HTTPError as exc:
                await self.say(chat, f"g{vi + 1}: arama hatası ({exc})")
                continue
            self.store.save(p)
            if not v.candidates:
                await self.say(
                    chat,
                    f"g{vi + 1} ({v.description}): aday bulunamadı. Fotoğraf gönder ya da "
                    f"`g{vi + 1}: başka açıklama` yazıp tekrar dene.",
                )
                continue
            for k, c in enumerate(v.candidates):
                try:
                    await self.bot.send_photo_url(
                        chat,
                        c.thumb_url,
                        f"g{vi + 1} · {v.description}\nAday {k + 1}: {c.title}\n{c.license}",
                        keyboard([(f"✅ g{vi + 1} için seç", f"pick:{p.id}:{vi}:{k}")]),
                    )
                except (httpx.HTTPError, RuntimeError):
                    continue
        await self.say(chat, "Seçimini yap, sonra 🎬 Render.", self._visual_buttons(p))

    async def start_render(self, chat: int, p: Project) -> None:
        problems = p.validate()
        missing = p.missing_visuals()
        if problems or missing:
            msg = "\n".join(problems)
            if missing:
                msg += "\nEksik görseller: " + ", ".join(f"g{i + 1}" for i in missing)
            await self.say(chat, f"⚠️ Render için hazır değil:\n{msg}", self._visual_buttons(p))
            return
        p.status = ProjectStatus.RENDERING
        self.store.save(p)
        if self.settings.studio_render_mode == "github":
            try:
                await dispatch_github(p, self.settings)
            except (RuntimeError, httpx.HTTPError) as exc:
                p.status = ProjectStatus.FAILED
                self.store.save(p)
                await self.say(chat, f"❌ GitHub Actions tetiklenemedi: {exc}")
                return
            await self.say(
                chat, "🚀 Render GitHub Actions'ta başladı (3-6 dk). Önizleme buraya gelecek."
            )
            return
        await self.say(chat, "🎬 Render başladı. İlerleme buradan güncellenecek.")
        task = asyncio.create_task(self._local_render(p))
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    async def _local_render(self, p: Project) -> None:
        path = write_project_file(p, self.store.workdir(p.id) / "input.json")
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app",
            "studio-render",
            "--project-file",
            str(path),
        )
        await proc.wait()

    # ------------------------------------------------------------ callbacks
    async def on_callback(self, chat: int, data: str) -> None:
        action, _, rest = data.partition(":")
        parts = rest.split(":")
        p = self.store.load(parts[0]) if parts and parts[0] else None
        if p is None:
            await self.say(chat, "Proje bulunamadı (sunucu yeniden başlamış olabilir).")
            return
        if action == "ok":
            p.status = ProjectStatus.COLLECTING
            self.store.save(p)
            await self.say(chat, visuals_status(p), self._visual_buttons(p))
        elif action == "rw":
            await self.say(chat, "✍️ Baştan yazılıyor…")
            try:
                fresh = await self.writer.write(p.topic, photos=user_photos_of(p))
            except LLMError as exc:
                await self.say(chat, f"❌ {exc}")
                return
            fresh.id, fresh.chat_id, fresh.created_at = p.id, p.chat_id, p.created_at
            self.store.save(fresh)
            await self.send_script(chat, fresh)
        elif action == "find":
            await self.find_candidates(chat, p)
        elif action == "pick" and len(parts) == 3:
            vi, k = int(parts[1]), int(parts[2])
            if 0 <= vi < len(p.visuals) and 0 <= k < len(p.visuals[vi].candidates):
                c = p.visuals[vi].candidates[k]
                v = p.visuals[vi]
                v.source, v.attribution, v.focus_x, v.focus_y = (
                    f"url:{c.url}",
                    c.attribution,
                    None,
                    None,
                )
                p.status = ProjectStatus.COLLECTING
                self.store.save(p)
                missing = p.missing_visuals()
                await self.say(
                    chat,
                    f"✅ g{vi + 1} seçildi."
                    + (
                        " Eksik: " + ", ".join(f"g{i + 1}" for i in missing)
                        if missing
                        else " Hepsi hazır!"
                    ),
                    None if missing else keyboard([("🎬 Render", f"render:{p.id}")]),
                )
        elif action in ("render", "rr"):
            if action == "rr" and p.youtube_id:
                yt = build_youtube(self.settings)
                if yt is not None:
                    try:
                        await yt.delete(p.youtube_id)
                    except httpx.HTTPError:
                        pass
                p.youtube_id = ""
            await self.start_render(chat, p)
        elif action == "plan" and len(parts) == 2:
            await self.ask_schedule(chat, p, parts[1])
        elif action == "pat" and len(parts) == 3:
            tz = schedule.local_tz(self.settings.studio_timezone)
            await self.schedule_at(chat, p, parts[1], schedule.decode(parts[2], tz))
        elif action == "cmt" and len(parts) == 2:
            await self.add_comment(chat, p, parts[1])
        elif action == "pub" and len(parts) == 2:
            await self.publish(chat, p, parts[1])
        elif action == "del" and len(parts) == 2:
            yt = build_youtube(self.settings)
            if yt is not None and parts[1] not in ("", "-"):
                try:
                    await yt.delete(parts[1])
                except httpx.HTTPError as exc:
                    await self.say(chat, f"⚠️ YouTube'dan silinemedi: {exc}")
            p.status = ProjectStatus.CANCELLED
            self.store.save(p)
            await self.say(chat, "🗑 İptal edildi.")

    # ------------------------------------------------------------ YouTube helpers
    def _now(self) -> datetime:
        return datetime.now(schedule.local_tz(self.settings.studio_timezone))

    async def check_youtube(self, chat: int) -> None:
        yt = build_youtube(self.settings)
        if yt is None:
            await self.say(
                chat, "❌ YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN eksik."
            )
            return
        try:
            channel = await yt.check()
        except (YouTubePublishError, httpx.HTTPError) as exc:
            await self.say(chat, f"❌ YouTube bağlantısı çalışmıyor:\n{exc}")
            return
        await self.say(
            chat,
            f"✅ YouTube bağlantısı çalışıyor · Kanal: {channel}\n"
            "(Bu test bu sunucudaki token'ı dener; render GitHub'daki secret'ı kullanır.)",
        )

    async def ask_schedule(self, chat: int, p: Project, video_id: str) -> None:
        if p.status == ProjectStatus.PUBLISHED:
            await self.say(
                chat,
                "Bu video zaten yayında. YouTube planlamayı yalnızca hiç yayınlanmamış gizli "
                "videolarda kabul ediyor.",
            )
            return
        if video_id in ("", "-"):
            await self.say(
                chat, "Video YouTube'a yüklenmemiş; önce /youtube ile bağlantıyı düzelt."
            )
            return
        rows = [
            [(label, f"pat:{p.id}:{video_id}:{schedule.encode(when)}")]
            for label, when in schedule.quick_options(self._now())
        ]
        await self.say(
            chat,
            "⏰ Ne zaman yayına girsin? (Türkiye saati)\n"
            "Başka bir saat için yaz: plan 18:30 · plan yarın 21:00 · plan 12.11 19:30",
            keyboard(*rows) if rows else None,
        )

    async def plan_from_text(self, chat: int, p: Project, when_text: str) -> None:
        when = schedule.parse_when(when_text, self._now())
        if when is None:
            await self.say(
                chat, "Saati anlayamadım. Örnek: plan 18:30 · plan yarın 21:00 · plan 12.11 19:30"
            )
            return
        if not p.youtube_id:
            await self.say(chat, "Bu projenin YouTube'da yüklü videosu yok; önce render + yükleme.")
            return
        await self.schedule_at(chat, p, p.youtube_id, when)

    async def schedule_at(self, chat: int, p: Project, video_id: str, when: datetime) -> None:
        if p.status == ProjectStatus.PUBLISHED:
            await self.say(
                chat,
                "Bu video zaten yayında. YouTube planlamayı yalnızca hiç yayınlanmamış gizli "
                "videolarda kabul ediyor.",
            )
            return
        if schedule.too_soon(when, self._now()):
            await self.say(chat, "Yayın saati en az 15 dakika sonrası olmalı.")
            return
        yt = build_youtube(self.settings)
        if yt is None:
            await self.say(chat, "YouTube bilgileri yok.")
            return
        try:
            await yt.schedule(video_id, schedule.to_rfc3339(when))
        except (YouTubePublishError, httpx.HTTPError) as exc:
            await self.say(chat, f"❌ {exc}")
            return
        p.youtube_id = video_id
        p.status = ProjectStatus.SCHEDULED
        p.scheduled_at = schedule.to_rfc3339(when)
        self.store.save(p)
        buttons = [[("🚀 Hemen yayınla", f"pub:{p.id}:{video_id}")]]
        if p.pinned_comment:
            buttons.append([("💬 Yorumu ekle (yayından sonra)", f"cmt:{p.id}:{video_id}")])
        await self.say(
            chat,
            f"⏰ Planlandı: {schedule.human(when)} (Türkiye saati)\n"
            f"YouTube o saatte herkese açacak: https://youtube.com/shorts/{video_id}\n"
            "Gizli videoya yorum eklenemiyor; yayına girince 💬 Yorumu ekle'ye bas.",
            keyboard(*buttons),
        )

    async def add_comment(self, chat: int, p: Project, video_id: str) -> None:
        yt = build_youtube(self.settings)
        if yt is None or not p.pinned_comment:
            await self.say(chat, "Eklenecek yorum ya da YouTube bilgisi yok.")
            return
        try:
            note = await yt.add_comment(video_id, p.pinned_comment)
        except (YouTubePublishError, httpx.HTTPError) as exc:
            note = f"Yorum eklenemedi: {exc}"
        await self.say(chat, f"💬 {note}")

    async def publish(self, chat: int, p: Project, video_id: str) -> None:
        yt = build_youtube(self.settings)
        if yt is None or video_id in ("", "-"):
            await self.say(
                chat, "YouTube bilgileri yok ya da video yüklenmemiş; elle yükleyebilirsin."
            )
            return
        try:
            notes = await yt.make_public(video_id, p.pinned_comment)
        except httpx.HTTPError as exc:
            await self.say(chat, f"❌ Yayınlanamadı: {exc}")
            return
        p.youtube_id = video_id
        p.status = ProjectStatus.PUBLISHED
        self.store.save(p)
        await self.say(
            chat,
            f"✅ Yayında: https://youtube.com/shorts/{video_id}\n"
            + "\n".join(f"• {n}" for n in notes),
        )
