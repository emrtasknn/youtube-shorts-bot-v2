from typing import Any

import pytest

from app.studio.llm import LLMError, parse_json_object
from app.studio.models import Project
from app.studio.script_writer import ScriptWriter, project_from_llm, split_topic_and_notes

LLM_OUTPUT: dict[str, Any] = {
    "title": "Ölümümü Gördüm",
    "description": "açıklama #shorts",
    "tags": ["röntgen", "tarih"],
    "pinned_comment": "Sence?",
    "thumbnail_text": "ÖLÜMÜMÜ GÖRDÜM",
    "thumbnail_visual": 2,
    "visuals": [
        {"description": "Röntgen portresi", "query": "Wilhelm Röntgen portrait"},
        {"description": "İlk el röntgeni", "query": "hand mit Ringen"},
    ],
    "lines": [
        {"narration": "Bu, tarihteki ilk insan röntgeni.", "visual": 2, "kicker": "İLK RÖNTGEN"},
        {"narration": "1895 yılında", "caption": "1895 yılında", "visual": 1, "era": "old"},
        {"narration": "iks", "card": "X", "visual": 9},
        {"narration": "", "visual": 1},
    ],
}


class FakeLLM:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.calls: list[str] = []

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls.append(user)
        return self.data


def test_project_from_llm_normalizes() -> None:
    p = project_from_llm(LLM_OUTPUT, "Röntgen")
    assert len(p.lines) == 3  # empty narration dropped
    assert p.lines[0].visual == 1  # 1-based -> 0-based
    assert p.lines[1].narration == "bin sekiz yüz doksan beş yılında"
    assert p.lines[1].shown == "1895 yılında"
    assert p.lines[2].card == "X"
    assert p.lines[2].visual == 1  # clamped
    assert p.thumbnail_visual == 1


def test_project_from_llm_requires_lines() -> None:
    with pytest.raises(LLMError):
        project_from_llm({"lines": []}, "x")


@pytest.mark.asyncio
async def test_revise_keeps_identity_and_sources() -> None:
    llm = FakeLLM(LLM_OUTPUT)
    writer = ScriptWriter(llm)
    p = await writer.write("Röntgen", "notlar")
    p.chat_id = 42
    p.visuals[0].source = "telegram:abc"
    revised = await writer.revise(p, "daha kısa")
    assert isinstance(revised, Project)
    assert revised.id == p.id and revised.chat_id == 42
    assert revised.visuals[0].source == "telegram:abc"
    assert "daha kısa" in llm.calls[-1]


def test_split_topic_and_notes() -> None:
    assert split_topic_and_notes("Emu Savaşı") == ("Emu Savaşı", "")
    topic, notes = split_topic_and_notes("Röntgen'in keşfi\n8 Kasım 1895'te...")
    assert topic == "Röntgen'in keşfi" and notes.startswith("8 Kasım")


def test_parse_json_object_handles_fences() -> None:
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(LLMError):
        parse_json_object("no json here")


@pytest.mark.asyncio
async def test_write_puts_user_photos_first() -> None:
    from app.studio.models import UserPhoto

    llm = FakeLLM(LLM_OUTPUT)
    photos = [
        UserPhoto("telegram:a", "Emu askerleri 1932"),
        UserPhoto("telegram:b"),
        UserPhoto("telegram:c", "Makineli tüfek"),
    ]
    p = await ScriptWriter(llm).write("Emu Savaşı", photos=photos)
    assert "KULLANICININ FOTOĞRAFLARI (3 adet" in llm.calls[-1]
    assert "Emu askerleri 1932" in llm.calls[-1]
    assert [v.source for v in p.visuals[:3]] == ["telegram:a", "telegram:b", "telegram:c"]
    # the model returned only 2 visuals: a 3rd slot is added for the extra photo
    assert p.visuals[2].description == "Makineli tüfek"


def test_user_photos_of_keeps_only_user_sources() -> None:
    from app.studio.models import Visual
    from app.studio.script_writer import user_photos_of

    p = Project(
        topic="t",
        visuals=[
            Visual("a", source="telegram:1"),
            Visual("b", source="url:https://x"),
            Visual("c"),
        ],
    )
    assert [ph.source for ph in user_photos_of(p)] == ["telegram:1"]
