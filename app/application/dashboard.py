"""Read-side query that combines both contexts into what the dashboard shows."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from app.application.unit_of_work import Clock, UnitOfWorkFactory
from app.domain.journal.entry import JournalEntry
from app.domain.practice.problem import Problem
from app.domain.practice.progress import ProgressReport, build_progress_report
from app.domain.streak import Streak, compute_streak
from app.domain.sync.state import SyncState

PROBLEMS_PER_DAY = 8


@dataclass(frozen=True)
class HeatCell:
    day: date
    solved: int
    journaled: bool
    future: bool

    @property
    def level(self) -> int:
        """0..4 intensity for the activity grid."""
        if self.future:
            return -1
        if self.solved == 0:
            return 1 if self.journaled else 0
        return min(4, 1 + (self.solved + 1) // 2)


@dataclass(frozen=True)
class Dashboard:
    today: date
    report: ProgressReport
    streak: Streak
    solved_today: int
    daily_target: int
    today_set: list[Problem]
    heatmap: list[list[HeatCell]]  # columns = weeks (Mon..Sun)
    today_entry: JournalEntry
    minutes_total: int
    sync: SyncState


def activity_grid(
    problems: list[Problem], entries: list[JournalEntry], today: date, weeks: int = 26
) -> list[list[HeatCell]]:
    solved = Counter(p.solved_on for p in problems if p.solved_on is not None)
    journaled = {e.day for e in entries if not e.is_empty}
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    grid: list[list[HeatCell]] = []
    for w in range(weeks):
        week = []
        for d in range(7):
            day = start + timedelta(weeks=w, days=d)
            week.append(HeatCell(day, solved.get(day, 0), day in journaled, day > today))
        grid.append(week)
    return grid


class DashboardQuery:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    def run(self) -> Dashboard:
        today = self._clock()
        with self._uow() as uow:
            problems = uow.problems.list_all()
            entries = uow.journal.list_all()
            sync = uow.sync_state.get()

        report = build_progress_report(problems)
        active = {p.solved_on for p in problems if p.solved_on} | {
            e.day for e in entries if not e.is_empty
        }
        focus_day = report.current_day or max((p.day for p in problems), default=1)
        today_entry = next((e for e in entries if e.day == today), JournalEntry(today))
        return Dashboard(
            today=today,
            report=report,
            streak=compute_streak(active, today),
            solved_today=sum(1 for p in problems if p.solved_on == today),
            daily_target=PROBLEMS_PER_DAY,
            today_set=[p for p in problems if p.day == focus_day],
            heatmap=activity_grid(problems, entries, today),
            today_entry=today_entry,
            minutes_total=sum(e.minutes for e in entries),
            sync=sync,
        )
