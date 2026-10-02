"""Routines: a task and when to run it.

    daily 08:00          every day
    weekdays 08:00       Monday to Friday
    weekends 10:00
    mon,thu 17:30        any days, by three-letter name
    every 30m            every 30 minutes (or 2h)

A time-of-day routine missed while your laptop slept runs once when it wakes,
the same day. It never runs twice for one day.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from shipmate.home import read_json, write_json

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
GROUPS = {
    "daily": set(range(7)),
    "everyday": set(range(7)),
    "weekdays": set(range(5)),
    "weekends": {5, 6},
}


@dataclass(frozen=True)
class Schedule:
    every: timedelta | None = None
    days: frozenset[int] = frozenset()
    at: time | None = None

    def is_due(self, last_run: datetime, now: datetime) -> bool:
        if self.every is not None:
            return now - last_run >= self.every
        assert self.at is not None
        if now.weekday() not in self.days:
            return False
        today = datetime.combine(now.date(), self.at)
        return last_run < today <= now


def parse(spec: str) -> Schedule:
    text = spec.strip().lower()
    interval = re.fullmatch(r"every\s+(\d+)\s*(m|min|mins|minutes?|h|hours?)", text)
    if interval:
        n, unit = int(interval.group(1)), interval.group(2)
        every = timedelta(hours=n) if unit.startswith("h") else timedelta(minutes=n)
        if every < timedelta(minutes=5):
            raise ValueError("The shortest interval is every 5m.")
        return Schedule(every=every)

    clock = re.fullmatch(r"(?:(.+?)\s+)?(?:at\s+)?(\d{1,2}):(\d{2})", text)
    if not clock:
        raise ValueError(
            f"Can't read {spec!r}. "
            "Try 'weekdays 08:00', 'daily 18:30', 'mon,thu 09:00' or 'every 30m'."
        )
    hour, minute = int(clock.group(2)), int(clock.group(3))
    if hour > 23 or minute > 59:
        raise ValueError(f"{hour}:{minute:02d} is not a time of day.")
    days: set[int] = set()
    for word in re.split(r"[,\s]+", clock.group(1) or "daily"):
        if word in GROUPS:
            days |= GROUPS[word]
        elif word[:3] in DAYS:
            days.add(DAYS.index(word[:3]))
        elif word:
            raise ValueError(f"Unknown day {word!r} in {spec!r}.")
    return Schedule(days=frozenset(days), at=time(hour, minute))


# ---------------------------------------------------------------- storage


def load() -> list[dict]:
    return read_json("routines.json", [])


def save(routines: list[dict]) -> None:
    write_json("routines.json", routines)


def add(when: str, task: str, allow: list[str] | None = None) -> dict:
    parse(when)  # refuse a schedule that will never run before saving it
    routines = load()
    next_id = max((int(r["id"]) for r in routines), default=0) + 1
    now = datetime.now().isoformat(timespec="seconds")
    routine = {
        "id": str(next_id),
        "when": when,
        "task": task,
        "allow": allow or [],
        "created": now,
        "last_run": now,  # so a new routine waits for its first slot
    }
    save([*routines, routine])
    return routine


def remove(routine_id: str) -> bool:
    routines = load()
    kept = [r for r in routines if r["id"] != routine_id]
    save(kept)
    return len(kept) != len(routines)


def due(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now()
    return [
        r for r in load() if parse(r["when"]).is_due(datetime.fromisoformat(r["last_run"]), now)
    ]


def mark_run(routine_id: str, when: datetime) -> None:
    routines = load()
    for r in routines:
        if r["id"] == routine_id:
            r["last_run"] = when.isoformat(timespec="seconds")
    save(routines)
