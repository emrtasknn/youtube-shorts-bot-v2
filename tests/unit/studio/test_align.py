import numpy as np
import pytest

from app.studio.align import RecognizedWord, align_line_words, build_aligner
from app.studio.models import Line
from app.studio.tts import SAMPLE_RATE, build_voice_track


def _rw(words: list[tuple[str, float, float]]) -> list[RecognizedWord]:
    return [RecognizedWord(w, s, e) for w, s, e in words]


def test_numbers_are_matched_through_spoken_form() -> None:
    rec = _rw(
        [
            ("Bin", 1.00, 1.20),
            ("sekiz", 1.20, 1.45),
            ("yüz", 1.45, 1.60),
            ("doksan", 1.60, 1.90),
            ("beş", 1.90, 2.05),
            ("yılında", 2.10, 2.60),
        ]
    )
    out = align_line_words("1895 yılında", 0.95, 2.70, 0, rec)
    assert [w.word for w in out] == ["1895", "yılında"]
    assert out[0].start == 1.0 and out[0].end == 2.05
    assert out[1].start == 2.1


def test_misheard_word_keeps_caption_text_and_unmatched_is_interpolated() -> None:
    rec = _rw(
        [("Vilhelm", 0.5, 0.9), ("rontgen", 0.9, 1.4), ("xyz", 1.5, 1.7), ("buldu", 2.4, 2.8)]
    )
    out = align_line_words("Wilhelm Röntgen ışınları buldu.", 0.4, 3.0, 2, rec)
    assert [w.word for w in out] == ["Wilhelm", "Röntgen", "ışınları", "buldu."]
    assert out[1].start == 0.9  # fuzzy match rontgen ~ röntgen
    assert out[1].end <= out[2].start < out[3].start == 2.4  # gap word interpolated
    assert all(a.end <= b.start + 1e-6 for a, b in zip(out, out[1:], strict=False))


def test_falls_back_to_syllables_without_recognition() -> None:
    out = align_line_words("Hiç duyulmadı", 0.0, 2.0, 0, [])
    assert len(out) == 2 and out[0].start == 0.0 and abs(out[-1].end - 2.0) < 0.01


def test_build_aligner_disabled_when_empty() -> None:
    assert build_aligner("") is None


class ToneTTS:
    name = "tone"

    async def synth(self, text: str) -> np.ndarray:
        n = int(SAMPLE_RATE * 0.2 * len(text.split()))
        return (0.3 * np.sin(np.arange(n) / SAMPLE_RATE * 2 * np.pi * 200)).astype(np.float32)


class FakeAligner:
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> list[RecognizedWord]:
        assert sample_rate == SAMPLE_RATE
        return _rw([("bir", 0.26, 0.40), ("iki", 0.40, 0.60), ("üç", 0.60, 0.64)])


class BrokenAligner:
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> list[RecognizedWord]:
        raise RuntimeError("model download failed")


@pytest.mark.asyncio
async def test_voice_track_uses_aligner_and_survives_failure() -> None:
    lines = [Line("bir iki üç")]
    track = await build_voice_track(lines, ToneTTS(), aligner=FakeAligner())
    assert track.alignment.startswith("whisper")
    assert track.words[0].start == 0.26 and track.words[1].start == 0.40
    broken = await build_voice_track(lines, ToneTTS(), aligner=BrokenAligner())
    assert broken.alignment.startswith("syllable") and len(broken.words) == 3
