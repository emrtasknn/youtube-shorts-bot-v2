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
    VoiceCast,
    VoiceRole,
    apply_effect,
    build_voice_track,
    level_clip,
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


# ------------------------------------------------------------------ voice cast
class _NamedTTS:
    """Plain tone whose loudness differs per voice; records what it was asked to read."""

    def __init__(self, name: str, amp: float = 0.5) -> None:
        self.name, self.amp, self.read = name, amp, []  # type: ignore[var-annotated]

    async def synth(self, text: str) -> Any:
        self.read.append(text)
        return _tone(0.3 * len(text.split())) * (self.amp / 0.5)


def _rms(x: Any) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


@pytest.mark.asyncio
async def test_cast_routes_each_line_to_its_role() -> None:
    narrator, vecihi, makam = _NamedTTS("ema"), _NamedTTS("fish"), _NamedTTS("piper")
    cast = VoiceCast(narrator, [VoiceRole("vecihi", vecihi), VoiceRole("MAKAM", makam)])
    lines = [
        Line(narration="anlatıcı konuşur"),
        Line(narration="ben uçtum", voice="vecihi"),
        Line(narration="on gün ev hapsi", voice="Makam"),
        Line(narration="hikâye sürer", voice="anlatici"),
    ]
    await build_voice_track(lines, cast)
    assert narrator.read == ["anlatıcı konuşur", "hikâye sürer"]
    assert vecihi.read == ["ben uçtum"]
    assert makam.read == ["on gün ev hapsi"]


@pytest.mark.asyncio
async def test_unknown_role_fails_before_any_audio() -> None:
    narrator = _NamedTTS("ema")
    cast = VoiceCast(narrator, [VoiceRole("vecihi", _NamedTTS("fish"))])
    lines = [Line(narration="bir"), Line(narration="iki", voice="spiker")]
    with pytest.raises(TTSError, match="spiker"):
        await build_voice_track(lines, cast)
    assert narrator.read == []


def test_turkish_role_names_match() -> None:
    cast = VoiceCast(_NamedTTS("ema"), [VoiceRole("VECİHİ", _NamedTTS("fish"))])
    assert cast.role_for(Line(narration="x", voice="Vecihi")).name == "vecihi"


def test_narrator_role_name_is_reserved() -> None:
    with pytest.raises(TTSError):
        VoiceCast(_NamedTTS("ema"), [VoiceRole("anlatici", _NamedTTS("fish"))])


def test_unknown_effect_is_rejected() -> None:
    with pytest.raises(TTSError, match="efekt"):
        VoiceRole("makam", _NamedTTS("piper"), effect="echo")


@pytest.mark.asyncio
async def test_multi_voice_levels_speakers_to_same_loudness() -> None:
    cast = VoiceCast(_NamedTTS("ema", amp=0.9), [VoiceRole("vecihi", _NamedTTS("fish", 0.05))])
    lines = [
        Line(narration="bir iki üç dört"),
        Line(narration="beş altı yedi sekiz", voice="vecihi"),
    ]
    track = await build_voice_track(lines, cast)
    a, b = track.lines
    sr = SAMPLE_RATE
    loud = _rms(track.audio[int(a.start * sr) : int(a.end * sr)])
    quiet = _rms(track.audio[int(b.start * sr) : int(b.end * sr)])
    assert loud == pytest.approx(quiet, rel=0.05)


@pytest.mark.asyncio
async def test_gain_db_shifts_a_role() -> None:
    cast = VoiceCast(_NamedTTS("ema"), [VoiceRole("vecihi", _NamedTTS("fish"), gain_db=-6)])
    lines = [Line(narration="bir iki üç"), Line(narration="dört beş altı", voice="vecihi")]
    track = await build_voice_track(lines, cast)
    a, b = track.lines
    sr = SAMPLE_RATE
    ratio = _rms(track.audio[int(b.start * sr) : int(b.end * sr)]) / _rms(
        track.audio[int(a.start * sr) : int(a.end * sr)]
    )
    assert ratio == pytest.approx(10 ** (-6 / 20), rel=0.05)


@pytest.mark.asyncio
async def test_speaker_change_adds_a_breath() -> None:
    same = VoiceCast(_NamedTTS("ema"), [VoiceRole("vecihi", _NamedTTS("fish"))])
    one = [Line(narration="bir iki"), Line(narration="üç dört")]
    two = [Line(narration="bir iki"), Line(narration="üç dört", voice="vecihi")]
    t1 = await build_voice_track(one, same)
    t2 = await build_voice_track(two, same)
    gap1 = t1.lines[1].start - t1.lines[0].end
    gap2 = t2.lines[1].start - t2.lines[0].end
    assert gap2 - gap1 == pytest.approx(0.25, abs=0.01)


def test_phone_effect_cuts_low_frequencies() -> None:
    t = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    bass = (0.5 * np.sin(2 * np.pi * 80 * t)).astype(np.float32)
    mid = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    assert _rms(apply_effect(bass, "phone")) < 0.1 * _rms(apply_effect(mid, "phone"))


def test_room_effect_adds_a_tail() -> None:
    x = _tone(0.5)
    y = apply_effect(x, "room")
    assert len(y) == len(x) + int(0.2 * SAMPLE_RATE)
    assert _rms(y[len(x) :]) > 0


def test_level_clip_never_exceeds_ceiling() -> None:
    spiky = np.zeros(SAMPLE_RATE, np.float32)
    spiky[100] = 1.0
    assert float(np.max(np.abs(level_clip(spiky)))) <= 0.95 + 1e-6


@pytest.mark.asyncio
async def test_mixed_cast_keeps_ema_timings_and_estimates_the_rest(
    fake_ema: type[_FakeEMA],
) -> None:
    cast = VoiceCast(ChainTTS([EmaLightningTTS()]), [VoiceRole("vecihi", _NamedTTS("fish"))])
    lines = [Line(narration="Röntgen eli gördü"), Line(narration="ben uçtum", voice="vecihi")]
    track = await build_voice_track(lines, cast)
    assert track.alignment.startswith("ema+hece")
    w0 = [w for w in track.words if w.line == 0]
    assert w0[1].start - w0[0].start == pytest.approx(0.4, abs=0.05)  # exact EMA timing
    assert [w.word for w in track.words if w.line == 1] == ["ben", "uçtum"]


@pytest.mark.asyncio
async def test_mixed_cast_uses_whisper_only_for_other_voices(fake_ema: type[_FakeEMA]) -> None:
    class Whisper:
        def transcribe(self, audio: Any, sample_rate: int) -> list[RecognizedWord]:
            # pretends to hear every line; words inside the EMA line must be ignored
            return [RecognizedWord("yanlış", 0.3, 0.5), RecognizedWord("ben", 99.0, 99.2)]

    cast = VoiceCast(ChainTTS([EmaLightningTTS()]), [VoiceRole("vecihi", _NamedTTS("fish"))])
    lines = [Line(narration="Röntgen eli gördü"), Line(narration="ben uçtum", voice="vecihi")]
    track = await build_voice_track(lines, cast, aligner=Whisper())
    assert track.alignment.startswith("ema+whisper")
    assert [w.word for w in track.words if w.line == 0] == ["Röntgen", "eli", "gördü"]


def test_cast_reports_who_spoke() -> None:
    cast = VoiceCast(_NamedTTS("ema"), [VoiceRole("vecihi", _NamedTTS("fish"))])
    assert cast.used == "anlatici: ema · vecihi: fish"
    assert VoiceCast(_NamedTTS("ema")).used == "ema"


@pytest.mark.asyncio
async def test_file_tts_reads_prerendered_lines(tmp_path: Any) -> None:
    import json as _json

    import soundfile as sf

    from app.studio.tts import FileTTS

    (tmp_path / "v1").mkdir()
    sf.write(str(tmp_path / "v1" / "a.wav"), _tone(0.5, sr=44100), 44100)
    key = FileTTS.key("On gün ev hapsi.")
    (tmp_path / "manifest.json").write_text(
        _json.dumps({"files": {"v1": {key: "a.wav"}}}), encoding="utf-8"
    )
    tts = FileTTS(tmp_path, "v1")
    audio = await tts.synth("On gün ev hapsi.")
    assert abs(len(audio) - SAMPLE_RATE // 2) < 200  # resampled to 48 kHz
    with pytest.raises(TTSError, match="hazır ses yok"):
        await tts.synth("başka bir cümle")
    with pytest.raises(TTSError):
        FileTTS(tmp_path, "yok")
