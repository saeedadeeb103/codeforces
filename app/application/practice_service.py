"""Use cases of the Practice context."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.application.unit_of_work import Clock, UnitOfWork, UnitOfWorkFactory
from app.domain.errors import NotFound
from app.domain.practice.problem import Problem
from app.domain.practice.value_objects import ProblemCode, Status


@dataclass(frozen=True)
class PlanFilter:
    status: Status | None = None
    topic_family: str | None = None
    day: int | None = None
    difficulty: str | None = None
    search: str | None = None

    def matches(self, p: Problem) -> bool:
        q = (self.search or "").strip().lower()
        return (
            (self.status is None or p.status == self.status)
            and (self.difficulty is None or p.rating.difficulty == self.difficulty)
            and (not q or q in p.name.lower() or q in p.code.value.lower() or q in p.topic.name.lower())
            and (self.topic_family is None or p.topic.family == self.topic_family)
            and (self.day is None or p.day == self.day)
        )


@dataclass(frozen=True)
class ProblemWork:
    notes: str
    solution: str
    language: str
    minutes: int
    solved_on: date | None = None
    status: Status | None = None  # optional: change status in the same save


class PracticeService:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    def plan(self, flt: PlanFilter | None = None) -> list[Problem]:
        with self._uow() as uow:
            problems = uow.problems.list_all()
        return [p for p in problems if flt is None or flt.matches(p)]

    def problem(self, code: str) -> Problem:
        with self._uow() as uow:
            return self._load(uow, code)

    def neighbours(self, code: str) -> tuple[Problem | None, Problem | None]:
        problems = self.plan()
        idx = next((i for i, p in enumerate(problems) if str(p.code) == ProblemCode(code).value), None)
        if idx is None:
            raise NotFound(code)
        prev = problems[idx - 1] if idx > 0 else None
        nxt = problems[idx + 1] if idx + 1 < len(problems) else None
        return prev, nxt

    def set_status(self, code: str, status: Status) -> Problem:
        with self._uow() as uow:
            problem = self._load(uow, code)
            problem.change_status(status, self._clock())
            uow.problems.save(problem)
            uow.commit()
            return problem

    def save_work(self, code: str, work: ProblemWork) -> Problem:
        with self._uow() as uow:
            problem = self._load(uow, code)
            if work.status is not None:
                problem.change_status(work.status, self._clock())
            problem.record_learning(work.notes)
            problem.attach_solution(work.solution, work.language)
            problem.log_time(work.minutes)
            if work.solved_on is not None and problem.is_done:
                problem.change_solved_date(work.solved_on, self._clock())
            uow.problems.save(problem)
            uow.commit()
            return problem

    def solved_between(self, days: Iterable[date]) -> dict[date, list[Problem]]:
        wanted = set(days)
        out: dict[date, list[Problem]] = {d: [] for d in wanted}
        for p in self.plan():
            if p.solved_on in wanted:
                out[p.solved_on].append(p)  # type: ignore[index]
        return out

    @staticmethod
    def _load(uow: UnitOfWork, code: str) -> Problem:
        problem = uow.problems.get(ProblemCode(code))
        if problem is None:
            raise NotFound(f"Problem {code} is not in the plan")
        return problem
