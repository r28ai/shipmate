from datetime import datetime, timedelta

import pytest

from shipmate import routines
from shipmate.routines import parse

FRIDAY = datetime(2026, 10, 2, 9, 0)  # a Friday, 09:00


def test_weekday_routine_runs_once_after_its_time():
    s = parse("weekdays 08:00")
    yesterday = FRIDAY - timedelta(days=1)
    assert s.is_due(last_run=yesterday, now=FRIDAY)  # missed 08:00 while asleep: catch up
    assert not s.is_due(last_run=FRIDAY.replace(hour=8, minute=1), now=FRIDAY)  # already ran


def test_weekday_routine_skips_the_weekend():
    saturday = FRIDAY + timedelta(days=1)
    assert not parse("weekdays 08:00").is_due(last_run=FRIDAY, now=saturday)
    assert parse("weekends 08:00").is_due(last_run=FRIDAY, now=saturday)


def test_named_days_and_bare_times():
    assert parse("mon,fri 08:30").days == frozenset({0, 4})
    assert parse("thursday at 17:00").days == frozenset({3})
    assert parse("07:15").days == frozenset(range(7))


def test_intervals():
    s = parse("every 30m")
    assert s.is_due(last_run=FRIDAY, now=FRIDAY + timedelta(minutes=30))
    assert not s.is_due(last_run=FRIDAY, now=FRIDAY + timedelta(minutes=29))
    assert parse("every 2h").every == timedelta(hours=2)


@pytest.mark.parametrize("spec", ["every 1m", "funday 08:00", "25:00", "whenever"])
def test_refuses_what_it_cannot_read(spec):
    with pytest.raises(ValueError):
        parse(spec)


def test_a_new_routine_waits_for_its_first_slot(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPMATE_HOME", str(tmp_path))
    routines.add("daily 00:00", "anything")
    assert routines.due() == []
