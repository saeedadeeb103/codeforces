"""Reads the 200-problem plan (exported from the Codeforces 200 Practice Plan sheet)."""

from __future__ import annotations

import csv
from pathlib import Path

from app.domain.practice.problem import Problem
from app.domain.practice.value_objects import ProblemCode, Rating, Topic

PLAN_CSV = Path(__file__).with_name("plan.csv")


def load_plan(path: Path = PLAN_CSV) -> list[Problem]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            Problem(
                code=ProblemCode(row["code"]),
                name=row["name"].replace("\\", "").strip(),
                topic=Topic(row["topic"]),
                rating=Rating(int(row["rating"])),
                day=int(row["day"]),
                position=i,
            )
            for i, row in enumerate(csv.DictReader(fh), start=1)
        ]
