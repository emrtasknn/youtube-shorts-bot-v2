from datetime import UTC, datetime, timedelta, timezone

from app.studio import schedule

TR = timezone(timedelta(hours=3))
NOW = datetime(2026, 11, 9, 18, 0, tzinfo=TR)  # Monday 18:00 in Istanbul


def test_parse_when_forms() -> None:
    assert schedule.parse_when("18:30", NOW) == NOW.replace(hour=18, minute=30)
    assert schedule.parse_when("17:00", NOW) == NOW.replace(day=10, hour=17)  # passed -> tomorrow
    assert schedule.parse_when("yarın 21:00", NOW) == NOW.replace(day=10, hour=21)
    assert schedule.parse_when("Yarin 09.15", NOW) == NOW.replace(day=10, hour=9, minute=15)
    assert schedule.parse_when("12.11 19:30", NOW) == NOW.replace(day=12, hour=19, minute=30)
    assert schedule.parse_when("1/1/2027 10:00", NOW) == datetime(2027, 1, 1, 10, tzinfo=TR)
    for bad in ("öğlen", "25:00", "31.02 10:00", "18"):
        assert schedule.parse_when(bad, NOW) is None


def test_quick_options_skip_past_and_too_soon() -> None:
    labels = [label for label, _ in schedule.quick_options(NOW)]
    assert labels == ["Bugün 19:00", "Bugün 21:00", "Yarın 12:00", "Yarın 19:00"]
    late = NOW.replace(hour=18, minute=50)
    assert [label for label, _ in schedule.quick_options(late)][0] == "Bugün 21:00"


def test_encode_roundtrip_and_utc() -> None:
    when = NOW.replace(hour=21)
    assert schedule.encode(when) == "202611091800"
    assert schedule.decode(schedule.encode(when), TR) == when
    assert schedule.to_rfc3339(when) == "2026-11-09T18:00:00Z"
    assert schedule.human(when) == "9 Kasım 21:00"
    assert schedule.too_soon(NOW + timedelta(minutes=5), NOW)
    assert not schedule.too_soon(NOW + timedelta(minutes=20), NOW)


def test_local_tz_is_utc_plus_3() -> None:
    now = datetime(2026, 7, 1, 12, tzinfo=UTC).astimezone(schedule.local_tz())
    assert now.utcoffset() == timedelta(hours=3)
