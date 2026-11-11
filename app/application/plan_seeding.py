"""Use case: make sure every problem of the plan exists, never touching your progress."""

from __future__ import annotations

from collections.abc import Iterable

from app.application.unit_of_work import UnitOfWorkFactory
from app.domain.practice.problem import Problem


def seed_plan(uow_factory: UnitOfWorkFactory, plan: Iterable[Problem]) -> int:
    """Insert problems that are missing; existing rows keep their status, notes and code."""
    with uow_factory() as uow:
        existing = uow.problems.existing_codes()
        added = 0
        for problem in plan:
            if problem.code not in existing:
                uow.problems.add(problem)
                added += 1
        uow.commit()
    return added
