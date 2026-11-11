from __future__ import annotations

from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from app.application.unit_of_work import UnitOfWork
from app.infrastructure.repositories import (
    SqlAlchemyJournalRepository,
    SqlAlchemyProblemRepository,
    SqlAlchemySyncStateRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory: sessionmaker) -> None:
        self._factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> Self:
        self._session = self._factory()
        self.problems = SqlAlchemyProblemRepository(self._session)
        self.journal = SqlAlchemyJournalRepository(self._session)
        self.sync_state = SqlAlchemySyncStateRepository(self._session)
        return self

    def __exit__(self, *exc: object) -> None:
        assert self._session is not None
        self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        assert self._session is not None
        self._session.commit()

    def rollback(self) -> None:
        assert self._session is not None
        self._session.rollback()
