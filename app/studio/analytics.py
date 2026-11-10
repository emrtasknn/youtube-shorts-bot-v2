"""/analiz: read a published Short's audience retention and say where viewers leave.

The YouTube Analytics API returns the retention curve as 100 points
(``elapsedVideoTimeRatio`` 0.01…1.0 -> ``audienceWatchRatio``). This module turns
that into three findings, the same split as Jake Schincariol's retention.py
(MIT): the hook leak (first seconds), the cliffs (single steep drops) and how
many made it to the end, plus the line that was being spoken at each cliff.

Line times are estimated from the narration (Turkish syllable weight), because
the exact render timeline lives on the render machine; the estimate is close
enough to name the sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.studio.models import Project
from app.studio.text import syllable_weight

HOOK_SECONDS = 3.0
CLIFF_WINDOW = 2.0  # seconds a drop is measured over
CLIFF_MIN = 0.05  # 5 points of the audience
LEAD_IN = 0.25

_VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})|^([A-Za-z0-9_-]{11})$")


def parse_video_id(text: str) -> str | None:
    m = _VIDEO_ID.search(text.strip())
    if not m:
        return None
    return m.group(1) or m.group(2)


def parse_duration(iso: str) -> float:
    """ISO 8601 'PT55S' / 'PT1M2S' -> seconds."""
    m = re.fullmatch(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", iso or "")
    if not m:
        return 0.0
    h, mi, s = (float(x) if x else 0.0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def line_spans(project: Project, duration: float) -> list[tuple[float, float]]:
    """Estimated (start, end) of each line, spread over the video by spoken length."""
    weights = [sum(syllable_weight(w) for w in ln.narration.split()) + 1.5 for ln in project.lines]
    total = sum(weights) or 1.0
    usable = max(duration - LEAD_IN, 0.1)
    spans, t = [], LEAD_IN
    for w in weights:
        d = usable * w / total
        spans.append((t, t + d))
        t += d
    return spans


@dataclass(slots=True)
class Cliff:
    start: float
    end: float
    drop: float  # fraction of the starting audience lost in the window
    line: int | None = None  # index into project.lines


@dataclass(slots=True)
class Retention:
    duration: float
    hook_kept: float  # share still watching at HOOK_SECONDS, relative to the start
    end_kept: float  # share still watching in the last 5%
    rewatch: bool  # the curve goes above the starting audience: people loop/replay
    cliffs: list[Cliff] = field(default_factory=list)


def analyze(points: list[tuple[float, float]], duration: float) -> Retention:
    """``points``: (elapsed ratio 0..1, audience watch ratio) from the Analytics API."""
    pts = sorted((r * duration, w) for r, w in points if w is not None)
    if not pts or duration <= 0:
        raise ValueError("boş izlenme eğrisi")
    start = pts[0][1] or 1.0

    def at(t: float) -> float:
        best = min(pts, key=lambda p: abs(p[0] - t))
        return best[1] / start

    tail = [w for t, w in pts if t >= duration * 0.95] or [pts[-1][1]]
    drops: list[Cliff] = []
    for t, _ in pts:
        if t < HOOK_SECONDS or t + CLIFF_WINDOW > duration:  # the hook is reported apart
            continue
        d = at(t) - at(t + CLIFF_WINDOW)
        if d >= CLIFF_MIN:
            drops.append(Cliff(round(t, 1), round(t + CLIFF_WINDOW, 1), round(d, 3)))
    cliffs: list[Cliff] = []
    for c in sorted(drops, key=lambda c: c.drop, reverse=True):
        if all(abs(c.start - k.start) >= CLIFF_WINDOW for k in cliffs):
            cliffs.append(c)
        if len(cliffs) == 3:
            break
    return Retention(
        duration=duration,
        hook_kept=round(at(min(HOOK_SECONDS, duration)), 3),
        end_kept=round(sum(tail) / len(tail) / start, 3),
        rewatch=max(w for _, w in pts) > start * 1.02,
        cliffs=sorted(cliffs, key=lambda c: c.start),
    )


def attach_lines(ret: Retention, project: Project) -> None:
    spans = line_spans(project, ret.duration)
    for c in ret.cliffs:
        mid = c.start  # the line being said when the drop starts
        for i, (a, b) in enumerate(spans):
            if a <= mid < b:
                c.line = i
                break


def pct(x: float) -> str:
    return f"%{round(x * 100)}"


def report(
    title: str,
    stats: dict[str, float],
    ret: Retention,
    project: Project | None,
) -> str:
    out = [f"📊 {title}"]
    views = int(stats.get("views", 0))
    avg_pct = stats.get("averageViewPercentage", 0.0)
    out.append(
        f"👁 {views:,} izlenme · ortalama izlenme %{round(avg_pct)} · "
        f"👍 {int(stats.get('likes', 0))} · ➕ {int(stats.get('subscribersGained', 0))} abone".replace(
            ",", "."
        )
    )
    out.append("")
    out.append(
        f"🪝 Kanca: ilk {int(HOOK_SECONDS)} saniyede izleyicilerin {pct(ret.hook_kept)}'i kaldı."
    )
    if ret.hook_kept < 0.7:
        out.append(
            "   → Açılış zayıf: ilk cümleyi kısalt, en şaşırtıcı bilgiyi ilk 2 saniyeye koy."
        )
    elif ret.hook_kept >= 0.85:
        out.append("   → Açılış güçlü, bu kalıbı koru.")
    if ret.cliffs:
        out.append("")
        out.append("📉 İzleyicinin en çok kaçtığı anlar:")
        for c in ret.cliffs:
            line = ""
            if project is not None and c.line is not None:
                line = f" — {c.line + 1}. satır: “{project.lines[c.line].shown[:70]}”"
            out.append(f"• {c.start:.0f}–{c.end:.0f}. sn: {pct(c.drop)} kayıp{line}")
        out.append("   → Bu satırları kısalt, görseli erken değiştir ya da sırayı değiştir.")
    else:
        out.append("")
        out.append("📉 Ani bir kopuş yok; izleyici kaybı dengeli.")
    out.append("")
    out.append(f"🏁 Sona kadar izleyen: {pct(ret.end_kept)}")
    if ret.rewatch or avg_pct > 100:
        out.append("🔁 Tekrar izleniyor: döngü (loop) kapanışı çalışıyor.")
    elif ret.end_kept < 0.3:
        out.append("   → Son kısım uzun kalıyor; videoyu 5–10 saniye kısaltmayı dene.")
    if project is None:
        out.append("\n(Bu video bir Studio projesine bağlı değil; satır eşleştirmesi yapılamadı.)")
    else:
        out.append("\n(Satır zamanları seslendirme uzunluğundan tahmin edildi.)")
    return "\n".join(out)
