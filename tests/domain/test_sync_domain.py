from datetime import date, datetime, timezone

import pytest

from app.domain.errors import DomainError
from app.domain.practice.submissions import SubmissionHistory, apply_submissions
from app.domain.practice.value_objects import ProblemCode, Status
from app.domain.sync.state import SyncState
from tests.fakes import make_problem

D = date(2026, 11, 11)


def test_accepted_marks_solved_with_first_ac_date_and_tried_marks_attempted():
    a = make_problem("4A", position=1)
    b = make_problem("71A", position=2)
    c = make_problem("231A", position=3)
    history = SubmissionHistory(
        first_accepted={ProblemCode("4A"): date(2026, 11, 3)},
        tried=frozenset({ProblemCode("4A"), ProblemCode("71A")}),
    )
    out = apply_submissions([a, b, c], history)
    assert [str(p.code) for p in out.solved] == ["4A"]
    assert [str(p.code) for p in out.attempted] == ["71A"]
    assert (a.status, a.solved_on) == (Status.SOLVED, date(2026, 11, 3))
    assert b.status is Status.ATTEMPTED and b.solved_on is None
    assert c.status is Status.TODO


def test_sync_never_touches_finished_or_downgrades_work():
    done = make_problem("4A", position=1, notes="mine")
    done.change_status(Status.REVIEW, D)
    attempted = make_problem("71A", position=2)
    attempted.change_status(Status.ATTEMPTED, D)
    history = SubmissionHistory(
        first_accepted={ProblemCode("4A"): date(2026, 1, 1)},
        tried=frozenset({ProblemCode("4A"), ProblemCode("71A")}),
    )
    out = apply_submissions([done, attempted], history)
    assert out.changed == []
    assert (done.status, done.solved_on, done.notes) == (Status.REVIEW, D, "mine")
    assert attempted.status is Status.ATTEMPTED


def test_attempted_problem_gets_solved_once_accepted():
    p = make_problem("4A")
    p.mark_attempted()
    apply_submissions([p], SubmissionHistory(first_accepted={ProblemCode("4A"): D}))
    assert (p.status, p.solved_on) == (Status.SOLVED, D)


@pytest.mark.parametrize("bad", ["", "ab", "x" * 25, "has space", "evil/../x"])
def test_sync_state_rejects_bad_handles(bad):
    with pytest.raises(DomainError):
        SyncState().connect(bad)


def test_changing_handle_resets_last_result():
    s = SyncState()
    s.connect("tourist")
    s.record_success(datetime(2026, 11, 11, tzinfo=timezone.utc), 5, 1)
    s.connect("tourist")
    assert s.last_solved == 5
    s.connect("Petr")
    assert (s.handle, s.last_synced_at, s.last_solved) == ("Petr", None, 0)
