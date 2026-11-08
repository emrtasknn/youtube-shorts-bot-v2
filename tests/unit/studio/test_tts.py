import sys
import types
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest

from app.studio.align import RecognizedWord
from app.studio.models import Line
from app.studio.tts import (
    SAMPLE_RATE,
    ChainTTS,
    EmaLightningTTS,
    Synthesis,
    TTSError,
    build_voice_track,
)


@dataclass
class _Word:
    text: str
    start: float
    end: float


@dataclass
class _Speech:
    audio: Any
    sample_rate: int
    words: list[_Word] = field(default_factory=list)
    seed: int = 0


def _tone(seconds: float, *, silence_before: float = 0.0, sr: int = SAMPLE_RATE) -> Any:
    lead = np.zeros(int(silence_before * sr), np.float32)
    t = np.arange(int(seconds * sr)) / sr
    return np.concatenate([lead, (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)])


class _FakeEMA:
    """Stands in for ema_lightning.EMA: 0.3 s silence, then 0.4 s per word."""

    calls: list[dict[str, Any]] = []

    def __init__(self, device: str = "auto") -> None:
        self.device = device

    def say(self, text: str, speed: float = 1.0, seed: Any = None, sample_rate: int = 48000):
        _FakeEMA.calls.append({"text": text, "speed": speed, "seed": seed, "sr": sample_rate})
        spoken = text.lower().split()
        words = [_Word(w, 0.3 + 0.4 * i, 0.3 + 0.4 * (i + 1)) for i, w in enumerate(spoken)]
        return _Speech(_tone(0.4 * len(spoken), silence_before=0.3), sample_rate, words)


@pytest.fixture
def fake_ema(monkeypatch: pytest.MonkeyPatch) -> type[_FakeEMA]:
    mod = types.ModuleType("ema_lightning")
    mod.EMA = _FakeEMA  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ema_lightning", mod)
    _FakeEMA.calls = []
    return _FakeEMA


class _PlainTTS:
    name = "plain"

    async def synth(self, text: str) -> Any:
        return _tone(0.3 * len(text.split()))


class _BrokenTTS:
    name = "broken"

    async def synth(self, text: str) -> Any:
        raise TTSError("down")


class _NoAligner:
    def transcribe(self, audio: Any, sample_rate: int) -> list[RecognizedWord]:
        raise AssertionError("whisper must not run when EMA gives word timings")


class _CountingAligner:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio: Any, sample_rate: int) -> list[RecognizedWord]:
        self.calls += 1
        return []


@pytest.mark.asyncio
async def test_ema_returns_audio_and_word_timings(fake_ema: type[_FakeEMA]) -> None:
    tts = EmaLightningTTS(speed=1.1, seed=42, device="cpu")
    syn = await tts.synth_detailed("Tarih çok garip")
    assert isinstance(syn, Synthesis)
    assert syn.backend == "ema"
    assert syn.audio.dtype == np.float32
    assert [w.word for w in syn.words or []] == ["tarih", "çok", "garip"]
    assert fake_ema.calls[-1] == {"text": "Tarih çok garip", "speed": 1.1, "seed": 42, "sr": 48000}


@pytest.mark.asyncio
async def test_ema_negative_seed_means_random(fake_ema: type[_FakeEMA]) -> None:
    await EmaLightningTTS(seed=-1).synth("merhaba")
    assert fake_ema.calls[-1]["seed"] is None


def test_ema_rejects_bad_speed() -> None:
    with pytest.raises(TTSError):
        EmaLightningTTS(speed=9)


@pytest.mark.asyncio
async def test_ema_resamples_other_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    class LowRate(_FakeEMA):
        def say(self, text: str, speed: float = 1.0, seed: Any = None, sample_rate: int = 48000):
            return _Speech(_tone(1.0, sr=24000), 24000, [])

    mod = types.ModuleType("ema_lightning")
    mod.EMA = LowRate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ema_lightning", mod)
    syn = await EmaLightningTTS().synth_detailed("bir")
    assert abs(len(syn.audio) - SAMPLE_RATE) < 10
    assert syn.words is None


@pytest.mark.asyncio
async def test_ema_load_failure_is_tts_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Offline:
        def __init__(self, device: str = "auto") -> None:
            raise OSError("no network for weights")

    mod = types.ModuleType("ema_lightning")
    mod.EMA = Offline  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ema_lightning", mod)
    with pytest.raises(TTSError, match="EMA yüklenemedi"):
        await EmaLightningTTS().synth("bir")


@pytest.mark.asyncio
async def test_voice_track_uses_ema_word_timings(fake_ema: type[_FakeEMA]) -> None:
    lines = [
        Line(narration="bin sekiz yüz doksan beşte", caption="1895'te"),
        Line(narration="iks", card="X"),
        Line(narration="Röntgen eli gördü"),
    ]
    track = await build_voice_track(lines, ChainTTS([EmaLightningTTS()]), aligner=_NoAligner())
    assert track.alignment == "ema (100%)"
    first, third = track.lines[0], track.lines[2]
    # the caption "1895'te" spans the whole first line (all five spoken words)
    w0 = [w for w in track.words if w.line == 0]
    assert [w.word for w in w0] == ["1895'te"]
    assert w0[0].start == pytest.approx(first.start, abs=0.05)
    assert w0[0].end == pytest.approx(first.end, abs=0.1)
    # leading silence is trimmed, so word times are shifted onto the clip, 0.4 s apart
    w2 = [w for w in track.words if w.line == 2]
    assert [w.word for w in w2] == ["Röntgen", "eli", "gördü"]
    assert w2[0].start == pytest.approx(third.start, abs=0.05)
    assert w2[1].start - w2[0].start == pytest.approx(0.4, abs=0.05)
    assert all(w.line != 1 for w in track.words)  # card lines have no caption words


@pytest.mark.asyncio
async def test_voice_track_falls_back_to_whisper_without_native_words() -> None:
    aligner = _CountingAligner()
    lines = [Line(narration="bir iki üç"), Line(narration="dört beş")]
    track = await build_voice_track(lines, ChainTTS([_BrokenTTS(), _PlainTTS()]), aligner=aligner)
    assert aligner.calls == 1
    assert track.alignment.startswith("whisper")


@pytest.mark.asyncio
async def test_chain_reports_backend_that_spoke(fake_ema: type[_FakeEMA]) -> None:
    chain = ChainTTS([_BrokenTTS(), EmaLightningTTS()])
    syn = await chain.synth_detailed("merhaba dünya")
    assert chain.used == "ema"
    assert syn.words is not None
