"""Turkish-aware text helpers used by timing, captions and thumbnails."""

from __future__ import annotations

import re
from dataclasses import dataclass

VOWELS = frozenset("aeıioöuüâîûAEIİOÖUÜÂÎÛ")
_ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]


def tr_upper(text: str) -> str:
    return text.replace("i", "İ").replace("ı", "I").upper()


def tr_lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def number_to_words(n: int) -> str:
    """Spell a non-negative integer in Turkish (up to billions)."""
    if n == 0:
        return "sıfır"
    parts: list[str] = []
    for value, name in ((10**9, "milyar"), (10**6, "milyon"), (1000, "bin")):
        q, n = divmod(n, value)
        if q:
            if not (value == 1000 and q == 1):
                parts.append(number_to_words(q))
            parts.append(name)
    h, n = divmod(n, 100)
    if h:
        if h > 1:
            parts.append(_ONES[h])
        parts.append("yüz")
    t, o = divmod(n, 10)
    if t:
        parts.append(_TENS[t])
    if o:
        parts.append(_ONES[o])
    return " ".join(parts)


def spell_numbers(text: str) -> str:
    """Make narration TTS-safe: '1895' -> 'bin sekiz yüz doksan beş'.

    Turkish suffixes after an apostrophe are kept ("1901'de" -> "bin dokuz yüz bir'de")
    which every TTS we use reads naturally.
    """
    return re.sub(r"\d+", lambda m: number_to_words(int(m.group())), text)


def syllable_weight(word: str) -> float:
    """Spoken-length estimate. In Turkish, syllables == vowels; digits are long."""
    vowels = sum(c in VOWELS for c in word)
    digits = sum(c.isdigit() for c in word)
    pause = 0.35 if word and word[-1] in ",.;:!?" else 0.0
    return max(vowels + 1.6 * digits, 1.0) + pause


@dataclass(frozen=True, slots=True)
class WordTiming:
    word: str
    start: float
    end: float
    line: int


def distribute_words(text: str, start: float, end: float, line: int) -> list[WordTiming]:
    words = text.split()
    if not words:
        return []
    weights = [syllable_weight(w) for w in words]
    total = sum(weights)
    out: list[WordTiming] = []
    cur = start
    for w, wt in zip(words, weights, strict=True):
        d = (end - start) * wt / total
        out.append(WordTiming(w, round(cur, 3), round(cur + d, 3), line))
        cur += d
    return out


def chunk_words(
    words: list[WordTiming], *, max_words: int = 3, max_chars: int = 19
) -> list[list[WordTiming]]:
    """Group words into short caption chunks, breaking at punctuation."""
    chunks: list[list[WordTiming]] = []
    cur: list[WordTiming] = []
    for w in words:
        cand = [*cur, w]
        txt = " ".join(x.word for x in cand)
        if cur and (len(cand) > max_words or len(txt) > max_chars or w.line != cur[0].line):
            chunks.append(cur)
            cur = [w]
        else:
            cur = cand
        if w.word[-1] in ",.!?;:":
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks
