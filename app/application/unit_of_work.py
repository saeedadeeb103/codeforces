"""Port for a transaction spanning both repositories. Infrastructure provides the adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import date
from typing import Self

from app.domain.journal.repository import JournalRepository
from app.domain.practice.repository import ProblemRepository
from app.domain.sync.repository import SyncStateRepository


class UnitOfWork(ABC):
    problems: ProblemRepository
    journal: JournalRepository
    sync_state: SyncStateRepository

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.rollback()  # no-op after commit

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
Clock = Callable[[], date]
