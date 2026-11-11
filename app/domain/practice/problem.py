"""The Problem aggregate: one problem of the practice plan and everything you did with it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.errors import DomainError
from app.domain.practice.value_objects import ProblemCode, Rating, Status, Topic

LANGUAGES = ("python", "cpp", "java", "kotlin", "go", "rust", "javascript", "other")
MAX_NOTES = 20_000
MAX_SOLUTION = 100_000


@dataclass
class Problem:
    code: ProblemCode
    name: str
    topic: Topic
    rating: Rating
    day: int
    position: int
    status: Status = Status.TODO
    solved_on: date | None = None
    notes: str = ""
    solution: str = ""
    language: str = "python"
    time_spent_minutes: int = 0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainError("Problem name cannot be empty")
        if self.day < 1:
            raise DomainError("Plan day starts at 1")
        if self.status.is_done != (self.solved_on is not None):
            raise DomainError("A problem has a solved date exactly when it is done")

    # --- queries ---------------------------------------------------------
    @property
    def url(self) -> str:
        return self.code.url

    @property
    def is_done(self) -> bool:
        return self.status.is_done

    # --- commands --------------------------------------------------------
    def change_status(self, new_status: Status, today: date) -> None:
        if new_status.is_done:
            if not self.is_done:
                self.solved_on = today
        else:
            self.solved_on = None
        self.status = new_status

    def mark_attempted(self) -> None:
        """You tried it but haven't solved it yet. Only moves a problem forward from To do."""
        if self.status is Status.TODO:
            self.status = Status.ATTEMPTED

    def change_solved_date(self, solved_on: date, today: date) -> None:
        if not self.is_done:
            raise DomainError("Only a solved problem has a solved date")
        if solved_on > today:
            raise DomainError("Solved date cannot be in the future")
        self.solved_on = solved_on

    def record_learning(self, notes: str) -> None:
        if len(notes) > MAX_NOTES:
            raise DomainError(f"Notes are limited to {MAX_NOTES} characters")
        self.notes = notes.strip()

    def attach_solution(self, code: str, language: str) -> None:
        if language not in LANGUAGES:
            raise DomainError(f"Unknown language '{language}'")
        if len(code) > MAX_SOLUTION:
            raise DomainError(f"Solutions are limited to {MAX_SOLUTION} characters")
        self.solution = code.rstrip()
        self.language = language

    def log_time(self, minutes: int) -> None:
        if not 0 <= minutes <= 24 * 60:
            raise DomainError("Time spent must be between 0 and 1440 minutes")
        self.time_spent_minutes = minutes
