"""Adapter for the public Codeforces API (https://codeforces.com/apiHelp/methods#user.status)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import date, datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from app.application.sync_service import SubmissionSource, SubmissionSourceError
from app.domain.errors import DomainError
from app.domain.practice.submissions import SubmissionHistory
from app.domain.practice.value_objects import ProblemCode

API_URL = "https://codeforces.com/api/user.status"


def parse_submissions(submissions: Iterable[dict[str, Any]], tz: ZoneInfo) -> SubmissionHistory:
    """Earliest accepted date per problem (in your time zone) + every problem you submitted to."""
    first_accepted: dict[ProblemCode, date] = {}
    tried: set[ProblemCode] = set()
    for sub in submissions:
        problem = sub.get("problem") or {}
        contest_id, index = problem.get("contestId"), problem.get("index")
        if contest_id is None or not index:
            continue  # e.g. acmsguru problems have no contest id
        try:
            code = ProblemCode(f"{contest_id}{index}")
        except DomainError:
            continue
        tried.add(code)
        if sub.get("verdict") == "OK":
            when = datetime.fromtimestamp(int(sub["creationTimeSeconds"]), tz=timezone.utc)
            day = when.astimezone(tz).date()
            if code not in first_accepted or day < first_accepted[code]:
                first_accepted[code] = day
    return SubmissionHistory(first_accepted=first_accepted, tried=frozenset(tried))


class CodeforcesApi(SubmissionSource):
    def __init__(
        self,
        tz: ZoneInfo,
        timeout: float = 20,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self._tz = tz
        self._timeout = timeout
        self._open = opener

    def fetch_history(self, handle: str) -> SubmissionHistory:
        request = Request(
            f"{API_URL}?{urlencode({'handle': handle})}",
            headers={"User-Agent": "cf-tracker/1.0", "Accept": "application/json"},
        )
        try:
            with self._open(request, timeout=self._timeout) as response:
                payload = json.load(response)
        except HTTPError as exc:
            # Codeforces answers bad handles with HTTP 400 and a JSON body explaining why.
            payload = self._json_or_none(exc)
            if payload is None:
                raise SubmissionSourceError(f"Codeforces answered HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise SubmissionSourceError("Couldn't reach Codeforces. Try again in a minute.") from exc
        except ValueError as exc:
            raise SubmissionSourceError("Codeforces sent a response that isn't JSON") from exc

        if payload.get("status") != "OK":
            raise SubmissionSourceError(payload.get("comment") or "Codeforces API error")
        return parse_submissions(payload.get("result") or [], self._tz)

    @staticmethod
    def _json_or_none(exc: HTTPError) -> dict[str, Any] | None:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
