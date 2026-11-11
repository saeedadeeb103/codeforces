"""Use cases of the Journal context."""

from __future__ import annotations

from datetime import date

from app.application.unit_of_work import Clock, UnitOfWorkFactory
from app.domain.errors import DomainError
from app.domain.journal.entry import JournalEntry


class JournalService:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    def today(self) -> date:
        return self._clock()

    def entry(self, day: date) -> JournalEntry:
        with self._uow() as uow:
            return uow.journal.get(day) or JournalEntry(day)

    def write(self, day: date, learned: str, minutes: int) -> JournalEntry:
        if day > self._clock():
            raise DomainError("You can't journal a day that hasn't happened yet")
        with self._uow() as uow:
            entry = uow.journal.get(day) or JournalEntry(day)
            entry.write(learned, minutes)
            if entry.is_empty:
                uow.journal.delete(day)
            else:
                uow.journal.save(entry)
            uow.commit()
            return entry

    def history(self) -> list[JournalEntry]:
        with self._uow() as uow:
            return uow.journal.list_all()
