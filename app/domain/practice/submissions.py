"""Domain service: fold your Codeforces submission history into the plan.

Rules:
- An accepted submission marks an unfinished problem as solved, dated by your first accept.
- Submissions without an accept move a "To do" problem to "Attempted".
- Sync never un-solves anything and never touches notes, code or problems you already finished.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from app.domain.practice.problem import Problem
from app.domain.practice.value_objects import ProblemCode, Status


@dataclass(frozen=True)
class SubmissionHistory:
    first_accepted: dict[ProblemCode, date] = field(default_factory=dict)
    tried: frozenset[ProblemCode] = frozenset()


@dataclass(frozen=True)
class SyncOutcome:
    solved: list[Problem]
    attempted: list[Problem]

    @property
    def changed(self) -> list[Problem]:
        return self.solved + self.attempted


def apply_submissions(problems: Iterable[Problem], history: SubmissionHistory) -> SyncOutcome:
    solved: list[Problem] = []
    attempted: list[Problem] = []
    for p in problems:
        if p.is_done:
            continue
        accepted_on = history.first_accepted.get(p.code)
        if accepted_on is not None:
            p.change_status(Status.SOLVED, accepted_on)
            solved.append(p)
        elif p.code in history.tried and p.status is Status.TODO:
            p.mark_attempted()
            attempted.append(p)
    return SyncOutcome(solved, attempted)
