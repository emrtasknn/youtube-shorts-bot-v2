"""Text-to-speech backends for Studio.

* ``ema``   — EMA Lightning (canberkkkkkk/ema-lightning, Apache-2.0). Turkish-only
  8.6M-parameter flow-matching model; runs on CPU. ``pip install ema-lightning``.
* ``fish``  — Fish Audio HTTP API (existing key in the repo).
* ``piper`` — offline Piper voice through sherpa-onnx (fallback, lower quality).

Each line is synthesized separately so line-level timing is exact; words inside a
line are timed by Turkish syllable weight (see ``text.distribute_words``).
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
import numpy as np
import numpy.typing as npt

from app.studio.align import Aligner, align_line_words, matched_ratio
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
    name = "ema"

    def __init__(self, *, sample_rate: int = SAMPLE_RATE) -> None:
        self._sr = sample_rate
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from ema_lightning import EMA
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise TTSError("ema-lightning kurulu değil: pip install ema-lightning") from exc
            self._model = EMA()
        return self._model

    def _synth_sync(self, text: str) -> Audio:
        model = self._load()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "line.wav"
            model.say(text, path=str(out))
            if not out.is_file():
                raise TTSError("EMA ses dosyası üretmedi")
            return _decode_to_array(out.read_bytes(), ".wav")

    async def synth(self, text: str) -> Audio:
        return await asyncio.to_thread(self._synth_sync, text)


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
        x = np.asarray(audio.samples, dtype=np.float32)
        sr = int(audio.sample_rate)
        if sr == SAMPLE_RATE:
            return x
        idx = np.linspace(0, len(x) - 1, int(len(x) * SAMPLE_RATE / sr))
        return np.interp(idx, np.arange(len(x)), x).astype(np.float32)

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

    async def synth(self, text: str) -> Audio:
        errors = []
        for b in self._backends:
            try:
                out = await b.synth(text)
                self.used = b.name
                return out
            except (TTSError, httpx.HTTPError, OSError) as exc:
                errors.append(f"{b.name}: {exc}")
        raise TTSError(" | ".join(errors))


# ------------------------------------------------------------------ voice track
def trim_silence(x: Audio, *, threshold: float = 0.012) -> Audio:
    if len(x) == 0:
        return x
    win = max(int(SAMPLE_RATE * 0.01), 1)
    env = np.convolve(np.abs(x), np.ones(win) / win, "same")
    idx = np.where(env > threshold * max(float(np.max(np.abs(x))), 1e-6) / 0.6)[0]
    if len(idx) == 0:
        return x
    a = max(int(idx[0]) - int(0.02 * SAMPLE_RATE), 0)
    b = min(int(idx[-1]) + int(0.05 * SAMPLE_RATE), len(x))
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
    for i, line in enumerate(lines):
        clip = trim_silence(await tts.synth(line.narration))
        peak = float(np.max(np.abs(clip))) if len(clip) else 0.0
        if peak > 0:
            clip = clip / peak * 0.9
        dur = len(clip) / SAMPLE_RATE
        timings.append(LineTiming(i, round(t, 3), round(t + dur, 3)))
        if not line.card:
            words.extend(distribute_words(line.shown, t, t + dur, i))
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
    if aligner is not None:
        await _apply_alignment(track, lines, aligner)
    return track


async def _apply_alignment(track: VoiceTrack, lines: list[Line], aligner: Aligner) -> None:
    """Replace syllable estimates with real word timings; keep estimates on failure."""
    try:
        recognized = await asyncio.to_thread(aligner.transcribe, track.audio, SAMPLE_RATE)
    except Exception as exc:  # optional feature: never fail the render
        track.alignment = f"syllable (whisper hata: {type(exc).__name__})"
        return
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
    track.alignment = f"whisper ({pct}%)"
