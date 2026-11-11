"""The Sync context: which Codeforces account to read and how the last sync went."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.domain.errors import DomainError

_HANDLE_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,24}$")


@dataclass
class SyncState:
    handle: str | None = None
    last_synced_at: datetime | None = None
    last_solved: int = 0
    last_attempted: int = 0
    last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self.handle is not None

    def connect(self, handle: str) -> None:
        handle = handle.strip()
        if not _HANDLE_RE.match(handle):
            raise DomainError(f"'{handle}' doesn't look like a Codeforces handle")
        if handle != self.handle:
            self.handle = handle
            self.last_synced_at = None
            self.last_solved = self.last_attempted = 0
            self.last_error = None

    def disconnect(self) -> None:
        self.handle = None
        self.last_synced_at = None
        self.last_solved = self.last_attempted = 0
        self.last_error = None

    def record_success(self, at: datetime, solved: int, attempted: int) -> None:
        self.last_synced_at = at
        self.last_solved = solved
        self.last_attempted = attempted
        self.last_error = None

    def record_failure(self, at: datetime, error: str) -> None:
        self.last_synced_at = at
        self.last_error = error[:300]
