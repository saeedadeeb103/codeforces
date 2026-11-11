"""Value objects of the Practice context: immutable, validated, compared by value."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.domain.errors import DomainError

_CODE_RE = re.compile(r"^(?P<contest>[1-9]\d*)(?P<index>[A-Z]\d?)$")


@dataclass(frozen=True, order=True)
class ProblemCode:
    """A Codeforces problem id such as ``4A`` or ``1249B1`` (contest id + index)."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if not _CODE_RE.match(normalized):
            raise DomainError(f"'{self.value}' is not a Codeforces problem code")
        object.__setattr__(self, "value", normalized)

    @property
    def contest_id(self) -> int:
        return int(_CODE_RE.match(self.value)["contest"])  # type: ignore[index]

    @property
    def index(self) -> str:
        return _CODE_RE.match(self.value)["index"]  # type: ignore[index]

    @property
    def url(self) -> str:
        return f"https://codeforces.com/problemset/problem/{self.contest_id}/{self.index}"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class Rating:
    """Codeforces difficulty: 800..3500 in steps of 100."""

    value: int

    def __post_init__(self) -> None:
        if not (800 <= self.value <= 3500 and self.value % 100 == 0):
            raise DomainError(f"{self.value} is not a Codeforces rating")

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class Topic:
    """A topic label like ``Graphs / BFS``. Its family (``Graphs``) groups related topics."""

    name: str

    def __post_init__(self) -> None:
        cleaned = " ".join(self.name.split())
        if not cleaned:
            raise DomainError("Topic cannot be empty")
        object.__setattr__(self, "name", cleaned)

    @property
    def family(self) -> str:
        return self.name.split(" / ")[0].strip()

    def __str__(self) -> str:
        return self.name


class Status(str, Enum):
    TODO = "todo"
    ATTEMPTED = "attempted"
    SOLVED = "solved"
    REVIEW = "review"  # solved, but worth revisiting

    @property
    def is_done(self) -> bool:
        return self in (Status.SOLVED, Status.REVIEW)

    @property
    def label(self) -> str:
        return {
            Status.TODO: "To do",
            Status.ATTEMPTED: "Attempted",
            Status.SOLVED: "Solved",
            Status.REVIEW: "Review again",
        }[self]
