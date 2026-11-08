"""Word timestamps from the real audio (faster-whisper) aligned to the known script.

Whisper transcribes the finished voice track with word timestamps; we then align
the *known* caption words to the recognized words (fuzzy, order-preserving
dynamic programming), so a misheard word never changes the caption text — it
only borrows timing. Caption numbers ("1895") are expanded to their spoken form
("bin sekiz yüz doksan beş") before matching. Words that cannot be matched are
interpolated between matched neighbours by Turkish syllable weight. Without
faster-whisper installed everything falls back to pure syllable weighting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from app.studio.text import WordTiming, distribute_words, spell_numbers, syllable_weight, tr_lower

_PUNCT = re.compile(r"[^\wçğıöşüâîû]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class RecognizedWord:
    word: str
    start: float
    end: float


class Aligner(Protocol):
    def transcribe(
        self, audio: npt.NDArray[np.float32], sample_rate: int
    ) -> list[RecognizedWord]: ...


def norm(word: str) -> str:
    return _PUNCT.sub("", tr_lower(word))


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _align_tokens(
    spoken: list[str], recognized: list[str], *, threshold: float = 0.6
) -> dict[int, int]:
    """Order-preserving fuzzy alignment; returns spoken index -> recognized index."""
    n, m = len(spoken), len(recognized)
    gap = -0.4
    score = np.zeros((n + 1, m + 1), np.float64)
    back = np.zeros((n + 1, m + 1), np.int8)  # 0 diag, 1 up (skip spoken), 2 left (skip rec)
    score[1:, 0] = gap * np.arange(1, n + 1)
    score[0, 1:] = gap * np.arange(1, m + 1)
    back[1:, 0] = 1
    back[0, 1:] = 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sim = similarity(spoken[i - 1], recognized[j - 1])
            diag = score[i - 1, j - 1] + (sim if sim >= threshold else -0.6)
            up = score[i - 1, j] + gap
            left = score[i, j - 1] + gap
            best = max(diag, up, left)
            score[i, j] = best
            back[i, j] = 0 if best == diag else (1 if best == up else 2)
    pairs: dict[int, int] = {}
    i, j = n, m
    while i > 0 and j > 0:
        b = back[i, j]
        if b == 0:
            if similarity(spoken[i - 1], recognized[j - 1]) >= threshold:
                pairs[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif b == 1:
            i -= 1
        else:
            j -= 1
    return pairs


def align_line_words(
    caption: str,
    start: float,
    end: float,
    line: int,
    recognized: list[RecognizedWord],
) -> list[WordTiming]:
    words = caption.split()
    if not words:
        return []
    in_line = [r for r in recognized if r.end > start - 0.15 and r.start < end + 0.15]
    if not in_line:
        return distribute_words(caption, start, end, line)

    spoken: list[str] = []
    owner: list[int] = []
    for wi, w in enumerate(words):
        for tok in spell_numbers(w).split():
            n = norm(tok)
            if n:
                spoken.append(n)
                owner.append(wi)
    rec_norm = [norm(r.word) for r in in_line]
    pairs = _align_tokens(spoken, rec_norm)

    anchors: dict[int, tuple[float, float]] = {}
    for si, ri in pairs.items():
        wi = owner[si]
        r = in_line[ri]
        s, e = max(r.start, start), min(r.end, end)
        if wi in anchors:
            s, e = min(s, anchors[wi][0]), max(e, anchors[wi][1])
        anchors[wi] = (s, e)

    # enforce monotonic anchors (drop any that go backwards)
    last_end = start
    for wi in sorted(anchors):
        s, e = anchors[wi]
        if s < last_end - 0.05 or e <= s:
            del anchors[wi]
            continue
        last_end = e

    out: list[WordTiming] = []
    i = 0
    while i < len(words):
        if i in anchors:
            s, e = anchors[i]
            out.append(WordTiming(words[i], round(s, 3), round(e, 3), line))
            i += 1
            continue
        j = i
        while j < len(words) and j not in anchors:
            j += 1
        left = out[-1].end if out else start
        right = anchors[j][0] if j < len(words) else end
        if right <= left:
            right = left + 0.08 * (j - i)
        weights = [syllable_weight(w) for w in words[i:j]]
        total = sum(weights)
        cur = left
        for w, wt in zip(words[i:j], weights, strict=True):
            d = (right - left) * wt / total
            out.append(WordTiming(w, round(cur, 3), round(cur + d, 3), line))
            cur += d
        i = j
    return out


def matched_ratio(
    caption: str, recognized: list[RecognizedWord], start: float, end: float
) -> float:
    """How much of a line Whisper heard — for logging/diagnostics."""
    in_line = [norm(r.word) for r in recognized if r.end > start - 0.15 and r.start < end + 0.15]
    spoken = [norm(t) for w in caption.split() for t in spell_numbers(w).split() if norm(t)]
    if not spoken:
        return 1.0
    return len(_align_tokens(spoken, in_line)) / len(spoken)


class FasterWhisperAligner:
    """faster-whisper on CPU (int8). ``pip install faster-whisper``."""

    def __init__(self, model_size: str = "base", *, compute_type: str = "int8") -> None:
        self._size, self._compute = model_size, compute_type
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self._size, device="cpu", compute_type=self._compute)
        return self._model

    def transcribe(self, audio: npt.NDArray[np.float32], sample_rate: int) -> list[RecognizedWord]:
        from scipy.signal import resample_poly

        x = np.asarray(audio, np.float32)
        if sample_rate != 16000:
            x = np.asarray(resample_poly(x, 16000, sample_rate), np.float32)
        segments, _ = self._load().transcribe(
            x, language="tr", word_timestamps=True, beam_size=1, vad_filter=False
        )
        out: list[RecognizedWord] = []
        for seg in segments:
            for w in seg.words or []:
                out.append(RecognizedWord(str(w.word).strip(), float(w.start), float(w.end)))
        return out


def build_aligner(model_size: str) -> Aligner | None:
    if not model_size:
        return None
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return None
    return FasterWhisperAligner(model_size)
