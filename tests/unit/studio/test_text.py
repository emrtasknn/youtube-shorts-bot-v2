from app.studio.text import (
    chunk_words,
    distribute_words,
    number_to_words,
    spell_numbers,
    syllable_weight,
    tr_upper,
)


def test_number_to_words_turkish() -> None:
    assert number_to_words(1895) == "bin sekiz yüz doksan beş"
    assert number_to_words(131) == "yüz otuz bir"
    assert number_to_words(2000000) == "iki milyon"
    assert number_to_words(1000) == "bin"


def test_spell_numbers_keeps_suffix() -> None:
    assert spell_numbers("1901'de verildi") == "bin dokuz yüz bir'de verildi"


def test_tr_upper_dotted_i() -> None:
    assert tr_upper("ilk ışık") == "İLK IŞIK"


def test_syllable_weight_counts_vowels_and_digits() -> None:
    assert syllable_weight("röntgen") == 2
    assert syllable_weight("1895") > syllable_weight("bin")


def test_distribute_and_chunk() -> None:
    words = distribute_words("Bu, tarihteki ilk insan röntgeni.", 1.0, 3.0, 0)
    assert words[0].start == 1.0
    assert abs(words[-1].end - 3.0) < 0.01
    chunks = chunk_words(words)
    assert [w.word for w in chunks[0]] == ["Bu,"]
    assert all(len(c) <= 3 for c in chunks)
