"""Use cases of the Sync context: connect a Codeforces handle and pull its submissions."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timedelta

from app.application.unit_of_work import UnitOfWorkFactory
from app.domain.errors import DomainError
from app.domain.practice.submissions import SubmissionHistory, apply_submissions
from app.domain.sync.state import SyncState

log = logging.getLogger(__name__)

MIN_INTERVAL = timedelta(seconds=30)  # Codeforces asks clients to go easy on the API


class SubmissionSourceError(RuntimeError):
    """The submission source could not be read (network, unknown handle, API down)."""


class SubmissionSource(ABC):
    """Port for wherever submissions come from; infrastructure talks to the Codeforces API."""

    @abstractmethod
    def fetch_history(self, handle: str) -> SubmissionHistory: ...


class SyncService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        source: SubmissionSource,
        now: Callable[[], datetime],
    ) -> None:
        self._uow = uow_factory
        self._source = source
        self._now = now
        self._lock = threading.Lock()

    def state(self) -> SyncState:
        with self._uow() as uow:
            return uow.sync_state.get()

    def connect(self, handle: str) -> SyncState:
        with self._uow() as uow:
            state = uow.sync_state.get()
            state.connect(handle)
            uow.sync_state.save(state)
            uow.commit()
        return self.sync(force=True)

    def disconnect(self) -> SyncState:
        with self._uow() as uow:
            state = uow.sync_state.get()
            state.disconnect()
            uow.sync_state.save(state)
            uow.commit()
            return state

    def sync(self, force: bool = False) -> SyncState:
        with self._lock:
            state = self.state()
            if not state.connected:
                raise DomainError("Connect your Codeforces handle first")
            now = self._now()
            if not force and state.last_synced_at and now - state.last_synced_at < MIN_INTERVAL:
                return state

            # Network call happens outside any database transaction.
            try:
                history = self._source.fetch_history(state.handle)  # type: ignore[arg-type]
            except SubmissionSourceError as exc:
                with self._uow() as uow:
                    state = uow.sync_state.get()
                    state.record_failure(now, str(exc))
                    uow.sync_state.save(state)
                    uow.commit()
                    return state

            with self._uow() as uow:
                outcome = apply_submissions(uow.problems.list_all(), history)
                for problem in outcome.changed:
                    uow.problems.save(problem)
                state = uow.sync_state.get()
                state.record_success(now, len(outcome.solved), len(outcome.attempted))
                uow.sync_state.save(state)
                uow.commit()
                log.info("Codeforces sync: %d solved, %d attempted", len(outcome.solved), len(outcome.attempted))
                return state

    def sync_if_connected(self) -> None:
        """For the background job: never raises."""
        try:
            if self.state().connected:
                self.sync()
        except Exception:  # noqa: BLE001
            log.exception("Background Codeforces sync failed")
