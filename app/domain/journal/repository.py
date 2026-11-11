from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.domain.journal.entry import JournalEntry


class JournalRepository(ABC):
    @abstractmethod
    def get(self, day: date) -> JournalEntry | None: ...

    @abstractmethod
    def save(self, entry: JournalEntry) -> None: ...

    @abstractmethod
    def delete(self, day: date) -> None: ...

    @abstractmethod
    def list_all(self) -> list[JournalEntry]:
        """Newest first."""
