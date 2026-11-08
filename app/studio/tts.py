"""Text-to-speech backends for Studio.

* ``ema``   — EMA Lightning (canberk7/ema-lightning, Apache-2.0). Turkish-only
  8.6M-parameter model; runs on CPU (~6x real time). ``pip install ema-lightning``.
  Besides the audio it returns exact word timings, which drive the captions.
* ``fish``  — Fish Audio HTTP API (existing key in the repo).
* ``piper`` — offline Piper voice through sherpa-onnx (fallback, lower quality).

Each line is synthesized separately so line-level timing is exact. Words inside a
line take their timing from the backend when it reports them (EMA), otherwise from
faster-whisper (``align.py``) or Turkish syllable weight (``text.distribute_words``).
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
import numpy as np
import numpy.typing as npt

from app.studio.align import Aligner, RecognizedWord, align_line_words, matched_ratio
from app.studio.models import Line
from app.studio.text import WordTiming, distribute_words

Audio = npt.NDArray[np.float32]
SAMPLE_RATE = 48000


class TTSError(RuntimeError):
    pass


class TTSBackend(Protocol):
    name: str

    async def synth(self, text: str) -> Audio:
        """Return mono float32 audio at ``SAMPLE_RATE``."""
        ...


@dataclass(slots=True)
class Synthesis:
    """Audio for one line plus, when the backend knows them, its word timings.

    ``words`` times are relative to the start of ``audio``; ``None`` means the
    backend gives no timings and the caller must estimate them.
    """

    audio: Audio
    words: list[RecognizedWord] | None = None
    backend: str = ""


async def synthesize(tts: TTSBackend, text: str) -> Synthesis:
    """Call ``synth_detailed`` when the backend has it, plain ``synth`` otherwise."""
    detailed = getattr(tts, "synth_detailed", None)
    if detailed is not None:
        result: Synthesis = await detailed(text)
        return result
    return Synthesis(await tts.synth(text), None, tts.name)


def _resample(x: Audio, sr: int) -> Audio:
    if sr == SAMPLE_RATE or len(x) == 0:
        return x
    idx = np.linspace(0, len(x) - 1, int(len(x) * SAMPLE_RATE / sr))
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


def _decode_to_array(data: bytes, suffix: str) -> Audio:
    """Decode any audio container via ffmpeg into mono float32 @ SAMPLE_RATE."""
    with tempfile.NamedTemporaryFile(suffix=suffix) as src:
        src.write(data)
        src.flush()
        proc = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                src.name,
                "-f",
                "f32le",
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                "-",
            ],
            capture_output=True,
            check=False,
        )
    if proc.returncode != 0:
        raise TTSError(f"ffmpeg decode failed: {proc.stderr.decode(errors='replace')[:300]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


class EmaLightningTTS:
    """EMA Lightning, in process. One model is loaded lazily and reused for every line.

    A fixed ``seed`` keeps the voice identical between a render and a re-render of the
    same text; ``speed`` is EMA's own tempo option (0.25-4).
    """

    name = "ema"

    def __init__(self, *, speed: float = 1.0, seed: int | None = 0, device: str = "auto") -> None:
        if not 0.25 <= speed <= 4:
            raise TTSError("EMA hızı 0.25 ile 4 arasında olmalı")
        if seed is not None and seed < 0:
            seed = None  # negative = random voice take every time
        self._speed, self._seed, self._device = speed, seed, device
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                try:
                    from ema_lightning import EMA
                except ImportError as exc:  # pragma: no cover - optional dependency
                    raise TTSError(
                        "ema-lightning kurulu değil: pip install -e '.[studio,ema]'"
                    ) from exc
                try:
                    self._model = EMA(device=self._device)
                except Exception as exc:  # weights download / torch errors
                    raise TTSError(f"EMA yüklenemedi: {type(exc).__name__}: {exc}") from exc
            return self._model

    def _synth_sync(self, text: str) -> Synthesis:
        model = self._load()
        try:
            speech = model.say(text, speed=self._speed, seed=self._seed, sample_rate=SAMPLE_RATE)
        except Exception as exc:
            raise TTSError(f"EMA hata: {type(exc).__name__}: {exc}") from exc
        audio = np.asarray(speech.audio, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            raise TTSError("EMA boş ses üretti")
        sr = int(getattr(speech, "sample_rate", SAMPLE_RATE))
        words = [
            RecognizedWord(str(w.text), float(w.start), float(w.end))
            for w in (getattr(speech, "words", None) or [])
        ]
        return Synthesis(_resample(audio, sr), words or None, self.name)

    async def synth_detailed(self, text: str) -> Synthesis:
        return await asyncio.to_thread(self._synth_sync, text)

    async def synth(self, text: str) -> Audio:
        return (await self.synth_detailed(text)).audio


class FishAudioTTS:
    name = "fish"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "s2.1-pro-free",
        reference_id: str = "",
        base_url: str = "https://api.fish.audio",
        timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise TTSError("FISH_AUDIO_API_KEY gerekli")
        self._key, self._model, self._ref = api_key, model, reference_id
        self._url, self._timeout = base_url.rstrip("/"), timeout

    async def synth(self, text: str) -> Audio:
        payload: dict[str, Any] = {"text": text, "format": "wav", "normalize": True}
        if self._ref:
            payload["reference_id"] = self._ref
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._url}/v1/tts",
                headers={"Authorization": f"Bearer {self._key}", "model": self._model},
                json=payload,
            )
        if r.status_code >= 400:
            raise TTSError(f"Fish Audio HTTP {r.status_code}: {r.text[:200]}")
        return await asyncio.to_thread(_decode_to_array, r.content, ".wav")


class PiperTTS:
    """Offline Piper voice via sherpa-onnx (model dir from k2-fsa/sherpa-onnx releases)."""

    name = "piper"

    def __init__(self, model_dir: Path, *, speed: float = 1.1) -> None:
        self._dir, self._speed = model_dir, speed
        self._tts: Any = None

    def _load(self) -> Any:
        if self._tts is None:
            try:
                import sherpa_onnx
            except ImportError as exc:  # pragma: no cover
                raise TTSError("sherpa-onnx kurulu değil (pip install 'sherpa-onnx<2')") from exc
            onnx = next(self._dir.glob("*.onnx"), None)
            if onnx is None:
                raise TTSError(f"Piper modeli bulunamadı: {self._dir}")
            cfg = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=str(onnx),
                        tokens=str(self._dir / "tokens.txt"),
                        data_dir=str(self._dir / "espeak-ng-data"),
                        noise_scale=0.6,
                        noise_scale_w=0.75,
                    ),
                    num_threads=2,
                ),
                max_num_sentences=2,
            )
            self._tts = sherpa_onnx.OfflineTts(cfg)
        return self._tts

    def _synth_sync(self, text: str) -> Audio:
        audio = self._load().generate(text, sid=0, speed=self._speed)
        return _resample(np.asarray(audio.samples, dtype=np.float32), int(audio.sample_rate))

    async def synth(self, text: str) -> Audio:
        return await asyncio.to_thread(self._synth_sync, text)


class ChainTTS:
    """Use the first backend; fall back to the next one if it fails."""

    def __init__(self, backends: list[TTSBackend]) -> None:
        if not backends:
            raise TTSError("Hiç TTS yapılandırılmamış")
        self._backends = backends
        self.name = "+".join(b.name for b in backends)
        self.used = ""

    async def synth_detailed(self, text: str) -> Synthesis:
        errors = []
        for b in self._backends:
            try:
                out = await synthesize(b, text)
            except (TTSError, httpx.HTTPError, OSError) as exc:
                errors.append(f"{b.name}: {exc}")
                continue
            self.used = b.name
            return out
        raise TTSError(" | ".join(errors))

    async def synth(self, text: str) -> Audio:
        return (await self.synth_detailed(text)).audio


# ------------------------------------------------------------------ voice track
def silence_bounds(x: Audio, *, threshold: float = 0.012) -> tuple[int, int]:
    """Sample range ``[a, b)`` of ``x`` without leading/trailing silence."""
    if len(x) == 0:
        return 0, 0
    win = max(int(SAMPLE_RATE * 0.01), 1)
    env = np.convolve(np.abs(x), np.ones(win) / win, "same")
    idx = np.where(env > threshold * max(float(np.max(np.abs(x))), 1e-6) / 0.6)[0]
    if len(idx) == 0:
        return 0, len(x)
    a = max(int(idx[0]) - int(0.02 * SAMPLE_RATE), 0)
    b = min(int(idx[-1]) + int(0.05 * SAMPLE_RATE), len(x))
    return a, b


def trim_silence(x: Audio, *, threshold: float = 0.012) -> Audio:
    a, b = silence_bounds(x, threshold=threshold)
    return x[a:b]


@dataclass(slots=True)
class LineTiming:
    index: int
    start: float
    end: float


@dataclass(slots=True)
class VoiceTrack:
    audio: Audio
    lines: list[LineTiming]
    words: list[WordTiming]
    alignment: str = "syllable"  # "whisper (87%)" when faster-whisper aligned the words

    @property
    def duration(self) -> float:
        return len(self.audio) / SAMPLE_RATE


async def build_voice_track(
    lines: list[Line],
    tts: TTSBackend,
    *,
    lead_in: float = 0.25,
    aligner: Aligner | None = None,
) -> VoiceTrack:
    pieces: list[Audio] = [np.zeros(int(lead_in * SAMPLE_RATE), np.float32)]
    t = lead_in
    timings: list[LineTiming] = []
    words: list[WordTiming] = []
    native: list[RecognizedWord] = []  # backend word timings, on the track's clock
    native_complete = True
    for i, line in enumerate(lines):
        syn = await synthesize(tts, line.narration)
        a, b = silence_bounds(syn.audio)
        clip = syn.audio[a:b]
        peak = float(np.max(np.abs(clip))) if len(clip) else 0.0
        if peak > 0:
            clip = clip / peak * 0.9
        dur = len(clip) / SAMPLE_RATE
        timings.append(LineTiming(i, round(t, 3), round(t + dur, 3)))
        if not line.card:
            words.extend(distribute_words(line.shown, t, t + dur, i))
            if syn.words:
                offset = t - a / SAMPLE_RATE
                native.extend(
                    RecognizedWord(
                        w.word,
                        min(max(w.start + offset, t), t + dur),
                        min(max(w.end + offset, t), t + dur),
                    )
                    for w in syn.words
                )
            else:
                native_complete = False
        pieces.append(clip.astype(np.float32))
        t += dur
        gap = 0.14
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if line.card or (nxt is not None and nxt.card):
            gap = 0.38
        if line.narration.rstrip().endswith((".", "!", "?")):
            gap += 0.06
        if nxt is None:
            gap = 0.15
        pieces.append(np.zeros(int(gap * SAMPLE_RATE), np.float32))
        t += gap
    audio = np.concatenate(pieces)
    track = VoiceTrack(audio, timings, words)
    if native and native_complete:
        # The TTS told us when every word is spoken: exact, no recognizer needed.
        _align_to(track, lines, native, "ema")
    elif aligner is not None:
        await _apply_alignment(track, lines, aligner)
    return track


def _align_to(
    track: VoiceTrack, lines: list[Line], recognized: list[RecognizedWord], source: str
) -> None:
    """Map caption words onto timed spoken words (numbers, case and punctuation may differ)."""
    words: list[WordTiming] = []
    ratios: list[float] = []
    for lt in track.lines:
        line = lines[lt.index]
        if line.card:
            continue
        words.extend(align_line_words(line.shown, lt.start, lt.end, lt.index, recognized))
        ratios.append(matched_ratio(line.shown, recognized, lt.start, lt.end))
    track.words = words
    pct = int(100 * sum(ratios) / max(len(ratios), 1))
    track.alignment = f"{source} ({pct}%)"


async def _apply_alignment(track: VoiceTrack, lines: list[Line], aligner: Aligner) -> None:
    """Replace syllable estimates with real word timings; keep estimates on failure."""
    try:
        recognized = await asyncio.to_thread(aligner.transcribe, track.audio, SAMPLE_RATE)
    except Exception as exc:  # optional feature: never fail the render
        track.alignment = f"syllable (whisper hata: {type(exc).__name__})"
        return
    _align_to(track, lines, recognized, "whisper")
