import json

import pytest

from app.config.settings import Settings
from app.studio.factory import build_cast, parse_voice_specs
from app.studio.tts import NARRATOR, TTSError


def _settings(voices: object, **kw: object) -> Settings:
    raw = voices if isinstance(voices, str) else json.dumps(voices)
    return Settings(studio_voices=raw, studio_tts="ema", **kw)  # type: ignore[arg-type]


def test_no_voices_means_narrator_only() -> None:
    cast = build_cast(_settings(""))
    assert list(cast.roles) == [NARRATOR]
    assert not cast.multi


def test_roles_get_their_own_backend_and_settings(tmp_path: object) -> None:
    cast = build_cast(
        _settings(
            {
                "vecihi": {"tts": "fish", "reference_id": "abc", "effect": "room", "gain_db": -1},
                "makam": {"tts": "piper", "piper_model_dir": "/m/fahrettin", "effect": "phone"},
            },
            fish_audio_api_key="k",
        )
    )
    assert set(cast.roles) == {NARRATOR, "vecihi", "makam"}
    vecihi = cast.roles["vecihi"]
    assert vecihi.tts.name == "fish" and vecihi.effect == "room" and vecihi.gain_db == -1
    fish = vecihi.tts._backends[0]  # type: ignore[attr-defined]
    assert fish._ref == "abc"
    assert cast.roles["makam"].tts.name == "piper"
    assert cast.roles[NARRATOR].tts.name == "ema"


def test_role_without_usable_backend_is_an_error() -> None:
    with pytest.raises(TTSError, match="vecihi"):
        build_cast(_settings({"vecihi": {"tts": "fish"}}))  # no FISH_AUDIO_API_KEY


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("{nope", "geçerli JSON"),
        ("[1, 2]", "JSON nesnesi"),
        ('{"vecihi": "fish"}', "vecihi"),
        ('{"vecihi": {"effect": "room"}}', "'tts' gerekli"),
        ('{"vecihi": {"tts": "fish", "pitch": 2}}', "pitch"),
    ],
)
def test_bad_voice_specs_name_the_problem(raw: str, message: str) -> None:
    with pytest.raises(TTSError, match=message):
        parse_voice_specs(raw)


def test_bad_effect_is_reported() -> None:
    with pytest.raises(TTSError, match="efekt"):
        build_cast(_settings({"makam": {"tts": "piper", "piper_model_dir": "/m", "effect": "x"}}))
