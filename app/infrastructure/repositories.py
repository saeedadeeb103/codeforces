"""SQLAlchemy adapters for the domain repositories. Rows never leave this module."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.journal.entry import JournalEntry
from app.domain.journal.repository import JournalRepository
from app.domain.practice.problem import Problem
from app.domain.practice.repository import ProblemRepository
from app.domain.practice.value_objects import ProblemCode, Rating, Status, Topic
from app.domain.sync.repository import SyncStateRepository
from app.domain.sync.state import SyncState
from app.infrastructure.db import JournalRow, ProblemRow, SyncStateRow


def _problem_from_row(row: ProblemRow) -> Problem:
    return Problem(
        code=ProblemCode(row.code),
        name=row.name,
        topic=Topic(row.topic),
        rating=Rating(row.rating),
        day=row.day,
        position=row.position,
        status=Status(row.status),
        solved_on=row.solved_on,
        notes=row.notes or "",
        solution=row.solution or "",
        language=row.language or "python",
        time_spent_minutes=row.time_spent_minutes or 0,
    )


def _copy_problem(problem: Problem, row: ProblemRow) -> None:
    row.code = problem.code.value
    row.name = problem.name
    row.topic = problem.topic.name
    row.rating = problem.rating.value
    row.day = problem.day
    row.position = problem.position
    row.status = problem.status.value
    row.solved_on = problem.solved_on
    row.notes = problem.notes
    row.solution = problem.solution
    row.language = problem.language
    row.time_spent_minutes = problem.time_spent_minutes


class SqlAlchemyProblemRepository(ProblemRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, code: ProblemCode) -> Problem | None:
        row = self._s.get(ProblemRow, code.value)
        return _problem_from_row(row) if row else None

    def list_all(self) -> list[Problem]:
        rows = self._s.scalars(select(ProblemRow).order_by(ProblemRow.position))
        return [_problem_from_row(r) for r in rows]

    def existing_codes(self) -> set[ProblemCode]:
        return {ProblemCode(c) for c in self._s.scalars(select(ProblemRow.code))}

    def add(self, problem: Problem) -> None:
        row = ProblemRow()
        _copy_problem(problem, row)
        self._s.add(row)

    def save(self, problem: Problem) -> None:
        row = self._s.get(ProblemRow, problem.code.value)
        if row is None:
            self.add(problem)
        else:
            _copy_problem(problem, row)


class SqlAlchemyJournalRepository(JournalRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, day: date) -> JournalEntry | None:
        row = self._s.get(JournalRow, day)
        return JournalEntry(row.day, row.learned or "", row.minutes or 0) if row else None

    def save(self, entry: JournalEntry) -> None:
        row = self._s.get(JournalRow, entry.day) or JournalRow(day=entry.day)
        row.learned = entry.learned
        row.minutes = entry.minutes
        self._s.add(row)

    def delete(self, day: date) -> None:
        self._s.execute(delete(JournalRow).where(JournalRow.day == day))

    def list_all(self) -> list[JournalEntry]:
        rows = self._s.scalars(select(JournalRow).order_by(JournalRow.day.desc()))
        return [JournalEntry(r.day, r.learned or "", r.minutes or 0) for r in rows]


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; everything is stored as UTC."""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


class SqlAlchemySyncStateRepository(SyncStateRepository):
    ROW_ID = 1

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self) -> SyncState:
        row = self._s.get(SyncStateRow, self.ROW_ID)
        if row is None:
            return SyncState()
        return SyncState(
            handle=row.handle,
            last_synced_at=_aware(row.last_synced_at),
            last_solved=row.last_solved or 0,
            last_attempted=row.last_attempted or 0,
            last_error=row.last_error,
        )

    def save(self, state: SyncState) -> None:
        row = self._s.get(SyncStateRow, self.ROW_ID) or SyncStateRow(id=self.ROW_ID)
        row.handle = state.handle
        row.last_synced_at = state.last_synced_at
        row.last_solved = state.last_solved
        row.last_attempted = state.last_attempted
        row.last_error = state.last_error
        self._s.add(row)
