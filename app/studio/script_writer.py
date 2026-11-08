"""Turn a topic (and optional source notes) into a Studio project script."""

from __future__ import annotations

import json
from typing import Any

from app.studio.llm import JsonLLM, LLMError
from app.studio.models import Era, Line, Project, UserPhoto, Visual
from app.studio.text import spell_numbers

SYSTEM_PROMPT = """Sen "Bir Garip Tarih" YouTube Shorts kanalının baş senaristisin.
Kanalın sloganı: "Tarih sandığınızdan çok daha garip." Amaç izleyiciyi sonuna kadar videoda tutmak.

KURALLAR
- Dil: Türkçe. Süre: 40-55 saniye (yaklaşık 110-150 kelime), 12-18 satır.
- 1. satır HOOK: en şok edici bilgi/alıntı/görüntü. Selam, giriş, "bugün size" YOK.
- Her satır tek bir görsel anına karşılık gelir, kısa ve vurucu cümleler kur.
- Gerilim kur: sorun -> tuhaf detay -> dönüm noktası -> sonuç.
- Tam olarak 1 satırı "card" anı yap: tek kelime/kısa ifade dev yazıyla ekrana patlar
  (örn. "X", "1.000.000", "YASAK"). O satırın narration'ı da sadece o kelimeyi okur.
- SON satır, videonun İLK satırına anlamca bağlanmalı (loop). Abone ol / beğen deme.
- Uydurma bilgi verme. Emin olmadığın tarihi/rakamı yazma. Kaynak notu verildiyse ona sadık kal.
- narration: TTS okuyacak. Rakamları YAZIYLA yaz ("bin sekiz yüz doksan beş"),
  yabancı isimleri Türkçe okunuşuyla yaz ("Vilhelm Röntgen", "Anna Berta").
- caption: ekranda görünen metin; rakam ve isimlerin doğru yazımı ("1895", "Wilhelm").
- kicker: ekranın üstünde küçük bağlam etiketi, BÜYÜK HARF, en fazla 32 karakter
  (örn. "8 KASIM 1895 · WÜRZBURG"). Aynı bölümde tekrar edebilir.
- era: "old" (arşiv/tarihi), "modern" (günümüz), "gold" (ödül/zafer anı).
- visuals: 6-10 görsel. Satırlar bunlara 1'den başlayan "visual" numarasıyla bağlanır;
  bir görsel birden çok satırda kullanılabilir. description Türkçe kısa tarif,
  query Wikimedia Commons'ta arama için İNGİLİZCE 2-5 kelime.
- title: en fazla 60 karakter, merak uyandıran, emoji en fazla 1.
- description: 2 kısa paragraf + son satırda 5-7 hashtag (#shorts dahil).
- tags: 12-18 Türkçe/İngilizce etiket. pinned_comment: tartışma başlatan bir soru.
- thumbnail_text: en fazla 4 kelime, en çarpıcı ifade. thumbnail_visual: kapak için görsel no.

SADECE şu şemada JSON döndür:
{"title": str, "description": str, "tags": [str], "pinned_comment": str,
 "thumbnail_text": str, "thumbnail_visual": int,
 "visuals": [{"description": str, "query": str}],
 "lines": [{"narration": str, "caption": str, "visual": int, "kicker": str,
            "era": "old"|"modern"|"gold", "card": str}]}
"""


def user_photos_prompt(photos: list[UserPhoto]) -> str:
    """Tell the writer which pictures the user already has; they become visuals 1..N."""
    rows = [
        f"{i}. {ph.note.strip() or 'açıklamasız fotoğraf (konuyla ilgili bir sahne)'}"
        for i, ph in enumerate(photos, 1)
    ]
    return (
        f"KULLANICININ FOTOĞRAFLARI ({len(photos)} adet, zaten elimizde):\n"
        + "\n".join(rows)
        + f"\nvisuals listesinin İLK {len(photos)} öğesi sırasıyla bu fotoğraflar olmalı "
        "(description'ı açıklamaya göre yaz). Hepsini satırlarda kullan; hikâyeyi bu "
        "görsellerin etrafında kur. Eksik kalan anlar için bunlardan SONRA yeni görseller ekle."
    )


def build_user_prompt(
    topic: str,
    notes: str = "",
    feedback: str = "",
    previous: str = "",
    photos: list[UserPhoto] | None = None,
) -> str:
    parts = [f"KONU: {topic.strip()}"]
    if notes.strip():
        parts.append(f"KAYNAK NOTLARI (bunlara sadık kal):\n{notes.strip()}")
    if photos:
        parts.append(user_photos_prompt(photos))
    if previous:
        parts.append(f"ÖNCEKİ TASLAK:\n{previous}")
    if feedback.strip():
        parts.append(f"DÜZELTME İSTEĞİ: {feedback.strip()}")
    return "\n\n".join(parts)


def project_from_llm(data: dict[str, Any], topic: str) -> Project:
    raw_visuals = data.get("visuals") or []
    raw_lines = data.get("lines") or []
    if not raw_lines:
        raise LLMError("Model satır üretmedi")
    visuals = [
        Visual(description=str(v.get("description", "")).strip(), query=str(v.get("query", "")))
        for v in raw_visuals
        if isinstance(v, dict)
    ]
    if not visuals:
        visuals = [Visual(description=topic, query=topic)]
    lines: list[Line] = []
    for raw in raw_lines:
        if not isinstance(raw, dict):
            continue
        narration = str(raw.get("narration", "")).strip()
        if not narration:
            continue
        caption = str(raw.get("caption", "")).strip() or narration
        spoken = spell_numbers(narration)
        try:
            vis = int(raw.get("visual", 1)) - 1
        except (TypeError, ValueError):
            vis = 0
        vis = min(max(vis, 0), len(visuals) - 1)
        try:
            era = Era(str(raw.get("era", "old")))
        except ValueError:
            era = Era.OLD
        lines.append(
            Line(
                narration=spoken,
                caption=caption if caption != spoken else "",
                visual=vis,
                kicker=str(raw.get("kicker", "")).strip()[:40],
                era=era,
                card=str(raw.get("card", "")).strip()[:14],
            )
        )
    try:
        thumb_vis = int(data.get("thumbnail_visual", 1)) - 1
    except (TypeError, ValueError):
        thumb_vis = 0
    return Project(
        topic=topic,
        lines=lines,
        visuals=visuals,
        title=str(data.get("title", topic))[:100],
        description=str(data.get("description", "")),
        tags=[str(t) for t in (data.get("tags") or [])][:25],
        pinned_comment=str(data.get("pinned_comment", "")),
        thumbnail_text=str(data.get("thumbnail_text", "")),
        thumbnail_visual=min(max(thumb_vis, 0), len(visuals) - 1),
    )


def script_as_json(project: Project) -> str:
    return json.dumps(
        {
            "title": project.title,
            "visuals": [{"description": v.description, "query": v.query} for v in project.visuals],
            "lines": [
                {
                    "narration": ln.narration,
                    "caption": ln.shown,
                    "visual": ln.visual + 1,
                    "kicker": ln.kicker,
                    "era": ln.era.value,
                    "card": ln.card,
                }
                for ln in project.lines
            ],
        },
        ensure_ascii=False,
    )


def attach_user_photos(project: Project, photos: list[UserPhoto]) -> None:
    """Put the user's photos into visuals 1..N (adding slots if the model made too few)."""
    for i, ph in enumerate(photos):
        if i >= len(project.visuals):
            project.visuals.append(Visual(description=ph.note or f"Senin fotoğrafın {i + 1}"))
        v = project.visuals[i]
        v.source, v.attribution, v.focus_x, v.focus_y = ph.source, "", None, None
        v.candidates = []
        if ph.note and not v.description:
            v.description = ph.note


def user_photos_of(project: Project) -> list[UserPhoto]:
    """Photos the user supplied to a project (kept when the script is rewritten)."""
    return [
        UserPhoto(v.source, v.description)
        for v in project.visuals
        if v.source.startswith(("telegram:", "file:"))
    ]


class ScriptWriter:
    def __init__(self, llm: JsonLLM) -> None:
        self._llm = llm

    async def write(
        self, topic: str, notes: str = "", photos: list[UserPhoto] | None = None
    ) -> Project:
        photos = photos or []
        data = await self._llm.complete_json(
            SYSTEM_PROMPT, build_user_prompt(topic, notes, photos=photos)
        )
        project = project_from_llm(data, topic)
        attach_user_photos(project, photos)
        return project

    async def revise(self, project: Project, feedback: str) -> Project:
        data = await self._llm.complete_json(
            SYSTEM_PROMPT,
            build_user_prompt(project.topic, feedback=feedback, previous=script_as_json(project)),
        )
        revised = project_from_llm(data, project.topic)
        # keep identity, chat and any visuals the user already supplied
        revised.id, revised.chat_id, revised.created_at = (
            project.id,
            project.chat_id,
            project.created_at,
        )
        for i, v in enumerate(revised.visuals):
            if i < len(project.visuals) and project.visuals[i].filled:
                v.source = project.visuals[i].source
        return revised


def split_topic_and_notes(message: str) -> tuple[str, str]:
    """'/yeni' accepts a one-line topic or a long pasted text (first line = topic)."""
    text = message.strip()
    if "\n" not in text and len(text) < 160:
        return text, ""
    first, _, rest = text.partition("\n")
    if len(first) > 160:
        return first[:120].rsplit(" ", 1)[0], text
    return first.strip(), rest.strip()
