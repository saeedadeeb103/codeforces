from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.sync.state import SyncState


class SyncStateRepository(ABC):
    @abstractmethod
    def get(self) -> SyncState:
        """The single sync state (a fresh one if none was saved yet)."""

    @abstractmethod
    def save(self, state: SyncState) -> None: ...
