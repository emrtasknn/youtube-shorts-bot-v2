"""Scheduled publishing times for Studio (YouTube ``status.publishAt``).

Times are entered and shown in the channel's local time (Europe/Istanbul by
default) and sent to YouTube in UTC. Turkey has no DST since 2016, so a fixed
UTC+3 is used when the system has no time zone database.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo

MIN_LEAD = timedelta(minutes=15)  # YouTube needs publishAt comfortably in the future
MONTHS = "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split()

_WHEN = re.compile(
    r"^\s*(?:(?P<rel>bugün|bugun|yarın|yarin)\s+|(?P<d>\d{1,2})[./](?P<m>\d{1,2})"
    r"(?:[./](?P<y>\d{4}))?\s+)?(?P<H>\d{1,2})[:.](?P<M>\d{2})\s*$",
    re.I,
)


def local_tz(name: str = "Europe/Istanbul") -> tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:  # no tz database in slim images
        return timezone(timedelta(hours=3), "TRT")


def parse_when(text: str, now: datetime) -> datetime | None:
    """'18:30', 'yarın 18:30', '12.11 18:30', '12.11.2027 18:30' -> aware local datetime.

    A bare time that already passed today means tomorrow.
    """
    m = _WHEN.match(text)
    if not m:
        return None
    hour, minute = int(m["H"]), int(m["M"])
    if hour > 23 or minute > 59:
        return None
    day = now.date()
    if m["rel"] and m["rel"].lower() in ("yarın", "yarin"):
        day += timedelta(days=1)
    elif m["d"]:
        try:
            day = day.replace(year=int(m["y"] or day.year), month=int(m["m"]), day=int(m["d"]))
        except ValueError:
            return None
    when = now.replace(
        year=day.year,
        month=day.month,
        day=day.day,
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    if not m["rel"] and not m["d"] and when <= now:
        when += timedelta(days=1)
    return when


def too_soon(when: datetime, now: datetime) -> bool:
    return when < now + MIN_LEAD


def quick_options(now: datetime) -> list[tuple[str, datetime]]:
    """A few sensible Shorts slots: today 19:00 if still ahead, then tomorrow."""
    out: list[tuple[str, datetime]] = []
    today = now.replace(second=0, microsecond=0)
    for label, days, hour in (
        ("Bugün 19:00", 0, 19),
        ("Bugün 21:00", 0, 21),
        ("Yarın 12:00", 1, 12),
        ("Yarın 19:00", 1, 19),
    ):
        when = (today + timedelta(days=days)).replace(hour=hour, minute=0)
        if not too_soon(when, now):
            out.append((label, when))
    return out


def human(when: datetime) -> str:
    return f"{when.day} {MONTHS[when.month - 1]} {when:%H:%M}"


def encode(when: datetime) -> str:
    """Compact UTC stamp for Telegram callback data (64-byte limit)."""
    return when.astimezone(UTC).strftime("%Y%m%d%H%M")


def decode(stamp: str, tz: tzinfo) -> datetime:
    return datetime.strptime(stamp, "%Y%m%d%H%M").replace(tzinfo=UTC).astimezone(tz)


def to_rfc3339(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
