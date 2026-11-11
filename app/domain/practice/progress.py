"""Domain service: how far along the plan you are, overall and per day, topic and rating."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass

from app.domain.practice.problem import Problem


@dataclass(frozen=True)
class Progress:
    label: str
    done: int
    total: int

    @property
    def percent(self) -> int:
        """Rounded down, so 100 means truly complete."""
        return 0 if self.total == 0 else self.done * 100 // self.total

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.done == self.total


@dataclass(frozen=True)
class ProgressReport:
    overall: Progress
    by_day: list[Progress]
    by_topic: list[Progress]
    by_rating: list[Progress]
    current_day: int | None  # first day with unfinished work; None when the plan is done
    total_days: int


def _group(
    problems: Sequence[Problem],
    key: Callable[[Problem], Hashable],
    label: Callable[[Hashable], str],
    sort_key: Callable[[Progress, Hashable], object],
) -> list[Progress]:
    buckets: dict[Hashable, list[Problem]] = defaultdict(list)
    for p in problems:
        buckets[key(p)].append(p)
    items = [
        (k, Progress(label(k), sum(p.is_done for p in ps), len(ps))) for k, ps in buckets.items()
    ]
    items.sort(key=lambda kv: sort_key(kv[1], kv[0]))  # type: ignore[arg-type,return-value]
    return [prog for _, prog in items]


def build_progress_report(problems: Sequence[Problem]) -> ProgressReport:
    overall = Progress("Overall", sum(p.is_done for p in problems), len(problems))
    by_day = _group(problems, lambda p: p.day, lambda d: f"Day {d}", lambda _, d: d)
    by_topic = _group(
        problems,
        lambda p: p.topic.family,
        str,
        lambda prog, fam: (-prog.total, fam),
    )
    by_rating = _group(problems, lambda p: p.rating.value, str, lambda _, r: r)
    unfinished_days = sorted({p.day for p in problems if not p.is_done})
    return ProgressReport(
        overall=overall,
        by_day=by_day,
        by_topic=by_topic,
        by_rating=by_rating,
        current_day=unfinished_days[0] if unfinished_days else None,
        total_days=len(by_day),
    )
