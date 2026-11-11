from datetime import date

import pytest

from app.application.dashboard import DashboardQuery, activity_grid
from app.application.journal_service import JournalService
from app.application.plan_seeding import seed_plan
from app.application.practice_service import PlanFilter, PracticeService, ProblemWork
from app.domain.errors import DomainError, NotFound
from app.domain.practice.value_objects import Status
from app.infrastructure.seed.plan_loader import load_plan
from tests.fakes import InMemoryUnitOfWork, make_problem

TODAY = date(2026, 11, 11)


@pytest.fixture
def uow():
    u = InMemoryUnitOfWork()
    seed_plan(u, [
        make_problem("4A", day=1, position=1),
        make_problem("71A", day=1, position=2, topic="Strings"),
        make_problem("263A", day=2, position=3),
    ])
    return u


@pytest.fixture
def practice(uow):
    return PracticeService(uow, lambda: TODAY)


def test_seeding_never_overwrites_progress(uow, practice):
    practice.set_status("4A", Status.SOLVED)
    practice.save_work("4A", ProblemWork("parity", "print('YES')", "python", 5))

    added = seed_plan(uow, [make_problem("4A", day=1, position=1), make_problem("1A", day=3, position=4)])

    assert added == 1
    p = practice.problem("4A")
    assert (p.status, p.notes, p.solution) == (Status.SOLVED, "parity", "print('YES')")
    assert [str(x.code) for x in practice.plan()] == ["4A", "71A", "263A", "1A"]


def test_status_and_work_are_committed(uow, practice):
    practice.set_status("71a", Status.ATTEMPTED)
    practice.save_work("71A", ProblemWork("abbreviate when len > 10", "code", "cpp", 12))
    p = practice.problem("71A")
    assert p.status is Status.ATTEMPTED
    assert (p.notes, p.language, p.time_spent_minutes) == ("abbreviate when len > 10", "cpp", 12)
    assert uow.commits >= 3  # seed + 2 writes


def test_backdating_a_solve(practice):
    practice.set_status("4A", Status.SOLVED)
    practice.save_work("4A", ProblemWork("", "", "python", 0, solved_on=date(2026, 11, 3)))
    assert practice.problem("4A").solved_on == date(2026, 11, 3)


def test_unknown_problem(practice):
    with pytest.raises(NotFound):
        practice.problem("9999Z")


def test_plan_filter(practice):
    practice.set_status("4A", Status.SOLVED)
    assert [str(p.code) for p in practice.plan(PlanFilter(status=Status.SOLVED))] == ["4A"]
    assert [str(p.code) for p in practice.plan(PlanFilter(topic_family="Strings"))] == ["71A"]
    assert [str(p.code) for p in practice.plan(PlanFilter(day=2))] == ["263A"]


def test_neighbours(practice):
    prev, nxt = practice.neighbours("71A")
    assert (str(prev.code), str(nxt.code)) == ("4A", "263A")
    assert practice.neighbours("4A")[0] is None


def test_journal_write_update_and_clear(uow):
    j = JournalService(uow, lambda: TODAY)
    j.write(TODAY, "binary search on answer", 45)
    assert j.entry(TODAY).minutes == 45
    j.write(TODAY, "binary search on answer + monotonic check", 60)
    assert [e.learned for e in j.history()] == ["binary search on answer + monotonic check"]
    j.write(TODAY, "", 0)  # emptying an entry removes it
    assert j.history() == []
    with pytest.raises(DomainError):
        j.write(date(2026, 11, 12), "from the future", 1)


def test_dashboard_combines_progress_streak_and_journal(uow, practice):
    practice.set_status("4A", Status.SOLVED)
    practice.set_status("71A", Status.SOLVED)
    JournalService(uow, lambda: TODAY).write(date(2026, 11, 10), "warm-up", 30)

    d = DashboardQuery(uow, lambda: TODAY).run()

    assert (d.report.overall.done, d.report.overall.total) == (2, 3)
    assert d.report.current_day == 2
    assert [str(p.code) for p in d.today_set] == ["263A"]
    assert d.solved_today == 2
    assert (d.streak.current, d.streak.active_today) == (2, True)
    assert d.minutes_total == 30


def test_activity_grid_shape_and_levels():
    p = make_problem()
    p.change_status(Status.SOLVED, TODAY)
    grid = activity_grid([p], [], TODAY, weeks=4)
    assert len(grid) == 4 and all(len(w) == 7 for w in grid)
    cells = {c.day: c for w in grid for c in w}
    assert cells[TODAY].solved == 1 and cells[TODAY].level == 2
    assert all(c.future for d, c in cells.items() if d > TODAY)
    assert grid[0][0].day.weekday() == 0  # columns start on Monday


def test_real_plan_file_is_consistent():
    plan = load_plan()
    assert len(plan) == 200
    assert len({p.code for p in plan}) == 200
    assert {p.day for p in plan} == set(range(1, 26))
    assert all(sum(p.day == d for p in plan) == 8 for d in range(1, 26))
    assert all("\\" not in p.name for p in plan)
    assert [p.position for p in plan] == list(range(1, 201))
