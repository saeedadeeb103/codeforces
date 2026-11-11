"""Domain service shared by both contexts: a day counts as active if you solved or journaled."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Streak:
    current: int
    longest: int
    active_today: bool


def compute_streak(active_days: Iterable[date], today: date) -> Streak:
    days = {d for d in active_days if d <= today}
    if not days:
        return Streak(0, 0, False)

    longest = run = 0
    previous: date | None = None
    for d in sorted(days):
        run = run + 1 if previous is not None and d - previous == timedelta(days=1) else 1
        longest = max(longest, run)
        previous = d

    # Today isn't over yet: a streak that reached yesterday is still alive.
    cursor = today if today in days else today - timedelta(days=1)
    current = 0
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)

    return Streak(current=current, longest=longest, active_today=today in days)
