from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.practice.problem import Problem
from app.domain.practice.value_objects import ProblemCode


class ProblemRepository(ABC):
    @abstractmethod
    def get(self, code: ProblemCode) -> Problem | None: ...

    @abstractmethod
    def list_all(self) -> list[Problem]:
        """All problems in plan order."""

    @abstractmethod
    def existing_codes(self) -> set[ProblemCode]: ...

    @abstractmethod
    def add(self, problem: Problem) -> None: ...

    @abstractmethod
    def save(self, problem: Problem) -> None: ...
