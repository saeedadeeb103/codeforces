from __future__ import annotations

import copy
from datetime import date

from app.application.unit_of_work import UnitOfWork
from app.domain.journal.entry import JournalEntry
from app.domain.journal.repository import JournalRepository
from app.domain.practice.problem import Problem
from app.domain.practice.repository import ProblemRepository
from app.domain.practice.value_objects import ProblemCode, Rating, Topic
from app.domain.sync.repository import SyncStateRepository
from app.domain.sync.state import SyncState


def make_problem(code: str = "4A", day: int = 1, position: int = 1, **kw) -> Problem:
    return Problem(
        code=ProblemCode(code),
        name=kw.pop("name", f"Problem {code}"),
        topic=Topic(kw.pop("topic", "Math")),
        rating=Rating(kw.pop("rating", 800)),
        day=day,
        position=position,
        **kw,
    )


class InMemoryProblems(ProblemRepository):
    def __init__(self) -> None:
        self.rows: dict[str, Problem] = {}

    def get(self, code: ProblemCode) -> Problem | None:
        p = self.rows.get(code.value)
        return copy.deepcopy(p) if p else None

    def list_all(self) -> list[Problem]:
        return [copy.deepcopy(p) for p in sorted(self.rows.values(), key=lambda p: p.position)]

    def existing_codes(self) -> set[ProblemCode]:
        return {ProblemCode(c) for c in self.rows}

    def add(self, problem: Problem) -> None:
        self.rows[problem.code.value] = copy.deepcopy(problem)

    def save(self, problem: Problem) -> None:
        self.rows[problem.code.value] = copy.deepcopy(problem)


class InMemoryJournal(JournalRepository):
    def __init__(self) -> None:
        self.rows: dict[date, JournalEntry] = {}

    def get(self, day: date) -> JournalEntry | None:
        e = self.rows.get(day)
        return copy.deepcopy(e) if e else None

    def save(self, entry: JournalEntry) -> None:
        self.rows[entry.day] = copy.deepcopy(entry)

    def delete(self, day: date) -> None:
        self.rows.pop(day, None)

    def list_all(self) -> list[JournalEntry]:
        return [copy.deepcopy(e) for e in sorted(self.rows.values(), key=lambda e: e.day, reverse=True)]


class InMemorySyncState(SyncStateRepository):
    def __init__(self) -> None:
        self.state = SyncState()

    def get(self) -> SyncState:
        return copy.deepcopy(self.state)

    def save(self, state: SyncState) -> None:
        self.state = copy.deepcopy(state)


class InMemoryUnitOfWork(UnitOfWork):
    """Commits by snapshot so a missing commit() is caught by tests."""

    def __init__(self) -> None:
        self._committed_problems = InMemoryProblems()
        self._committed_journal = InMemoryJournal()
        self._committed_sync = InMemorySyncState()
        self.commits = 0

    def __call__(self) -> InMemoryUnitOfWork:
        return self

    def __enter__(self) -> InMemoryUnitOfWork:
        self.problems = copy.deepcopy(self._committed_problems)
        self.journal = copy.deepcopy(self._committed_journal)
        self.sync_state = copy.deepcopy(self._committed_sync)
        return self

    def commit(self) -> None:
        self._committed_problems = copy.deepcopy(self.problems)
        self._committed_journal = copy.deepcopy(self.journal)
        self._committed_sync = copy.deepcopy(self.sync_state)
        self.commits += 1

    def rollback(self) -> None:
        pass


class FakeSubmissionSource:
    """Stands in for the Codeforces API."""

    def __init__(self, history=None, error: str | None = None) -> None:
        from app.domain.practice.submissions import SubmissionHistory

        self.history = history or SubmissionHistory()
        self.error = error
        self.calls: list[str] = []

    def fetch_history(self, handle: str):
        from app.application.sync_service import SubmissionSourceError

        self.calls.append(handle)
        if self.error:
            raise SubmissionSourceError(self.error)
        return self.history
