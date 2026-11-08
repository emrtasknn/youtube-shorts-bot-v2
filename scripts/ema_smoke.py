"""Real EMA Lightning check: download the weights, voice two lines, verify word timings.

Run: python scripts/ema_smoke.py [out.wav]
Exits non-zero if EMA does not load, returns no audio, or gives no word timings.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from app.studio.models import Line
from app.studio.tts import SAMPLE_RATE, EmaLightningTTS, build_voice_track

LINES = [
    Line(
        narration="Bin dokuz yüz otuz iki yılında Avustralya ordusu emulara savaş açtı.",
        caption="1932'de Avustralya ordusu emulara savaş açtı.",
    ),
    Line(narration="kaybetti", card="KAYBETTİ"),
    Line(narration="Ve bu savaşı kuşlar kazandı."),
]


async def main(out: Path) -> int:
    tts = EmaLightningTTS(device="cpu")
    t0 = time.perf_counter()
    syn = await tts.synth_detailed(LINES[0].narration)
    print(f"EMA loaded + first line in {time.perf_counter() - t0:.1f}s")
    if syn.audio.size == 0 or float(np.max(np.abs(syn.audio))) < 0.01:
        print("FAIL: EMA returned silent/empty audio")
        return 1
    if not syn.words:
        print("FAIL: EMA returned no word timings")
        return 1
    for w in syn.words:
        print(f"  {w.start:5.2f} {w.end:5.2f}  {w.word}")

    track = await build_voice_track(LINES, tts)
    print(f"track: {track.duration:.2f}s, alignment: {track.alignment}")
    for w in track.words:
        print(f"  line {w.line}  {w.start:6.2f} {w.end:6.2f}  {w.word}")
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, track.audio, SAMPLE_RATE)
    print(f"wrote {out}")
    if not track.alignment.startswith("ema"):
        print("FAIL: captions did not use EMA word timings")
        return 1
    starts = [w.start for w in track.words]
    if starts != sorted(starts) or any(w.end <= w.start for w in track.words):
        print("FAIL: word timings are not increasing")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("storage/ema_smoke.wav")
    sys.exit(asyncio.run(main(target)))
