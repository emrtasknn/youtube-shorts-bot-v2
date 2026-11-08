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


def test_split_script_lines_one_shot_per_sentence() -> None:
    from app.studio.script_writer import split_script_lines

    text = (
        "1932'de Avustralya ordusu emulara savaş açtı. Hedef 20.000 kuştu!\n\n"
        "- Ve bu savaşı kuşlar kazandı."
    )
    assert split_script_lines(text) == [
        "1932'de Avustralya ordusu emulara savaş açtı.",
        "Hedef 20.000 kuştu!",
        "Ve bu savaşı kuşlar kazandı.",
    ]
    long = " ".join(f"kelime{i}," if i == 9 else f"kelime{i}" for i in range(30))
    parts = split_script_lines(long)
    assert parts[0].endswith("kelime9,")  # cut at the comma first
    assert [len(x.split()) for x in parts] == [10, 10, 10]  # then balanced, no 2-word tail


def test_project_from_script_without_photos() -> None:
    from app.studio.script_writer import project_from_script

    p = project_from_script("Emu Savaşı", "1932'de savaş başladı. Emular kazandı.")
    assert p.title == "Emu Savaşı" and len(p.lines) == 2
    assert p.lines[0].caption == "1932'de savaş başladı."
    assert "bin dokuz yüz otuz iki" in p.lines[0].narration
    assert [ln.visual for ln in p.lines] == [0, 1]
    assert p.missing_visuals() == [0, 1]
    assert p.validate() == []


def test_project_from_script_spreads_lines_over_pool_photos() -> None:
    from app.studio.models import UserPhoto
    from app.studio.script_writer import project_from_script

    script = "Bir. İki. Üç. Dört. Beş."
    photos = [UserPhoto("telegram:a", "Emu"), UserPhoto("telegram:b")]
    p = project_from_script("Emu", script, photos)
    assert [ln.visual for ln in p.lines] == [0, 0, 0, 1, 1]
    assert [v.source for v in p.visuals] == ["telegram:a", "telegram:b"]
    assert p.missing_visuals() == []


def test_project_from_script_requires_text() -> None:
    from app.studio.script_writer import project_from_script

    with pytest.raises(LLMError):
        project_from_script("Başlık", "   \n  ")


@pytest.mark.asyncio
async def test_groq_retries_without_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from app.studio.llm import GroqLLM

    bodies: list[dict[str, Any]] = []
    replies = [
        httpx.Response(400, json={"error": {"code": "json_validate_failed"}}),
        httpx.Response(200, json={"choices": [{"message": {"content": '```json\n{"a": 1}\n```'}}]}),
    ]

    async def fake_post(self: Any, body: dict[str, Any]) -> httpx.Response:
        bodies.append(dict(body))
        return replies.pop(0)

    monkeypatch.setattr(GroqLLM, "_post", fake_post)
    assert await GroqLLM("k").complete_json("sys", "user") == {"a": 1}
    assert "response_format" in bodies[0] and "response_format" not in bodies[1]


def test_studio_models_fall_back_to_shared_settings() -> None:
    from app.config.settings import Settings
    from app.studio.factory import build_llm

    s = Settings(
        groq_api_key="g", gemini_api_key="m", groq_model="llama-x", gemini_model="gemini-new"
    )
    groq, gemini = build_llm(s)._providers  # type: ignore[attr-defined]
    assert groq._model == "llama-x" and gemini._model == "gemini-new"
    s2 = Settings(
        groq_api_key="g",
        gemini_api_key="m",
        studio_groq_model="studio-groq",
        studio_gemini_model="studio-gem",
    )
    groq, gemini = build_llm(s2)._providers  # type: ignore[attr-defined]
    assert groq._model == "studio-groq" and gemini._model == "studio-gem"


@pytest.mark.asyncio
async def test_groq_body_and_error_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from app.studio.llm import GroqLLM

    bodies: list[dict[str, Any]] = []

    async def fake_post(self: Any, body: dict[str, Any]) -> httpx.Response:
        bodies.append(dict(body))
        msg = {"content": None, "reasoning": "thinking..."}
        return httpx.Response(200, json={"choices": [{"message": msg, "finish_reason": "length"}]})

    monkeypatch.setattr(GroqLLM, "_post", fake_post)
    with pytest.raises(LLMError, match="finish_reason=length, 0 karakter"):
        await GroqLLM("k", model="openai/gpt-oss-20b").complete_json("s", "u")
    assert bodies[0]["reasoning_effort"] == "low" and bodies[0]["max_completion_tokens"] == 8192
    with pytest.raises(LLMError):
        await GroqLLM("k", model="llama-3.3-70b-versatile").complete_json("s", "u")
    assert "reasoning_effort" not in bodies[1]
