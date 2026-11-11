"""The Journal context: one entry per calendar day about what you learned and how long you coded."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.errors import DomainError

MAX_TEXT = 20_000


@dataclass
class JournalEntry:
    day: date
    learned: str = ""
    minutes: int = 0

    def __post_init__(self) -> None:
        self.write(self.learned, self.minutes)

    def write(self, learned: str, minutes: int) -> None:
        if len(learned) > MAX_TEXT:
            raise DomainError(f"Journal entries are limited to {MAX_TEXT} characters")
        if not 0 <= minutes <= 24 * 60:
            raise DomainError("Minutes coded must be between 0 and 1440")
        self.learned = learned.strip()
        self.minutes = minutes

    @property
    def is_empty(self) -> bool:
        return not self.learned and self.minutes == 0
