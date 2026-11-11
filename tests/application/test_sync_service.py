import io
import json
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

import pytest

from app.application.plan_seeding import seed_plan
from app.application.sync_service import SubmissionSourceError, SyncService
from app.domain.errors import DomainError
from app.domain.practice.submissions import SubmissionHistory
from app.domain.practice.value_objects import ProblemCode, Status
from app.infrastructure.codeforces import CodeforcesApi, parse_submissions
from tests.fakes import FakeSubmissionSource, InMemoryUnitOfWork, make_problem

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


@pytest.fixture
def uow():
    u = InMemoryUnitOfWork()
    seed_plan(u, [make_problem("4A", position=1), make_problem("71A", position=2)])
    return u


def test_connect_syncs_and_records_result(uow):
    source = FakeSubmissionSource(SubmissionHistory(
        first_accepted={ProblemCode("4A"): date(2026, 11, 3)},
        tried=frozenset({ProblemCode("4A"), ProblemCode("71A")}),
    ))
    svc = SyncService(uow, source, Clock())
    state = svc.connect("tourist")
    assert source.calls == ["tourist"]
    assert (state.last_solved, state.last_attempted, state.last_error) == (1, 1, None)
    with uow as u:
        assert u.problems.get(ProblemCode("4A")).solved_on == date(2026, 11, 3)
        assert u.problems.get(ProblemCode("71A")).status is Status.ATTEMPTED


def test_sync_requires_a_handle(uow):
    with pytest.raises(DomainError):
        SyncService(uow, FakeSubmissionSource(), Clock()).sync()


def test_failure_is_recorded_not_raised(uow):
    svc = SyncService(uow, FakeSubmissionSource(error="handle: User with handle x not found"), Clock())
    state = svc.connect("nobody_here")
    assert "not found" in state.last_error
    with uow as u:
        assert all(p.status is Status.TODO for p in u.problems.list_all())


def test_sync_is_throttled_unless_forced(uow):
    clock = Clock()
    source = FakeSubmissionSource()
    svc = SyncService(uow, source, clock)
    svc.connect("tourist")
    svc.sync()
    assert len(source.calls) == 1  # within 30s: skipped
    clock.now += timedelta(seconds=31)
    svc.sync()
    assert len(source.calls) == 2


def test_background_sync_never_raises(uow):
    svc = SyncService(uow, FakeSubmissionSource(), Clock())
    svc.sync_if_connected()  # not connected: no-op
    svc.connect("tourist")


# --- Codeforces adapter -------------------------------------------------------
def _sub(contest, index, verdict, ts):
    return {"problem": {"contestId": contest, "index": index}, "verdict": verdict, "creationTimeSeconds": ts}


def test_parse_takes_earliest_accept_in_local_time():
    late_evening_utc = int(datetime(2026, 11, 3, 23, 30, tzinfo=timezone.utc).timestamp())  # 00:30 Nov 4 Berlin
    later = int(datetime(2026, 11, 9, 10, tzinfo=timezone.utc).timestamp())
    h = parse_submissions([
        _sub(4, "A", "WRONG_ANSWER", 1),
        _sub(4, "A", "OK", later),
        _sub(4, "A", "OK", late_evening_utc),
        _sub(1249, "B1", "TIME_LIMIT_EXCEEDED", later),
        {"problem": {"index": "A"}, "verdict": "OK", "creationTimeSeconds": later},  # no contest id
        _sub(4, "", "OK", later),
    ], BERLIN)
    assert h.first_accepted == {ProblemCode("4A"): date(2026, 11, 4)}
    assert h.tried == {ProblemCode("4A"), ProblemCode("1249B1")}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(body=None, exc=None):
    def open_(request, timeout):
        assert "handle=tourist" in request.full_url and timeout == 20
        if exc:
            raise exc
        return _Resp(json.dumps(body).encode())
    return open_


def test_api_success():
    api = CodeforcesApi(BERLIN, opener=_opener({"status": "OK", "result": [_sub(4, "A", "OK", 1_700_000_000)]}))
    assert ProblemCode("4A") in api.fetch_history("tourist").first_accepted


def test_api_reports_codeforces_comment_on_http_400():
    body = io.BytesIO(json.dumps({"status": "FAILED", "comment": "handle: User with handle tourist not found"}).encode())
    err = HTTPError("u", 400, "Bad Request", {}, body)
    with pytest.raises(SubmissionSourceError, match="not found"):
        CodeforcesApi(BERLIN, opener=_opener(exc=err)).fetch_history("tourist")


def test_api_network_error():
    with pytest.raises(SubmissionSourceError, match="Couldn't reach"):
        CodeforcesApi(BERLIN, opener=_opener(exc=URLError("down"))).fetch_history("tourist")


def test_api_failed_status():
    with pytest.raises(SubmissionSourceError, match="Call limit"):
        CodeforcesApi(BERLIN, opener=_opener({"status": "FAILED", "comment": "Call limit exceeded"})).fetch_history("tourist")
