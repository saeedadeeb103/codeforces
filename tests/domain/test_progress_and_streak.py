from datetime import date, timedelta

from app.domain.practice.progress import Progress, build_progress_report
from app.domain.practice.value_objects import Status
from app.domain.streak import compute_streak
from tests.fakes import make_problem

D = date(2026, 11, 11)


def _solved(p, on=D):
    p.change_status(Status.SOLVED, on)
    return p


def test_percent_rounds_down_so_100_means_done():
    assert Progress("x", 199, 200).percent == 99
    assert Progress("x", 200, 200).percent == 100
    assert Progress("x", 0, 0).percent == 0


def test_report_groups_by_day_topic_family_and_rating():
    problems = [
        _solved(make_problem("4A", day=1, position=1, topic="Graphs / DFS", rating=800)),
        make_problem("71A", day=1, position=2, topic="Graphs / BFS", rating=900),
        _solved(make_problem("1A", day=2, position=3, topic="Math", rating=800)),
        make_problem("2A", day=2, position=4, topic="Math", rating=1000),
        make_problem("3A", day=2, position=5, topic="Math", rating=1000),
    ]
    r = build_progress_report(problems)
    assert (r.overall.done, r.overall.total) == (2, 5)
    assert [(p.label, p.done, p.total) for p in r.by_day] == [("Day 1", 1, 2), ("Day 2", 1, 3)]
    # biggest topic families first
    assert [(p.label, p.done, p.total) for p in r.by_topic] == [("Math", 1, 3), ("Graphs", 1, 2)]
    assert [p.label for p in r.by_rating] == ["800", "900", "1000"]
    assert r.current_day == 1


def test_current_day_skips_finished_days_and_is_none_when_done():
    a = _solved(make_problem("4A", day=1, position=1))
    b = make_problem("71A", day=2, position=2)
    assert build_progress_report([a, b]).current_day == 2
    _solved(b)
    assert build_progress_report([a, b]).current_day is None


def test_streak_counts_consecutive_days_through_yesterday():
    days = [D - timedelta(days=i) for i in (1, 2, 3)] + [D - timedelta(days=10)]
    s = compute_streak(days, D)
    assert (s.current, s.longest, s.active_today) == (3, 3, False)


def test_streak_breaks_after_a_missed_day():
    s = compute_streak([D - timedelta(days=2), D - timedelta(days=3)], D)
    assert (s.current, s.longest) == (0, 2)


def test_streak_includes_today_and_ignores_future():
    s = compute_streak([D, D - timedelta(days=1), D + timedelta(days=1)], D)
    assert (s.current, s.longest, s.active_today) == (2, 2, True)


def test_empty_streak():
    s = compute_streak([], D)
    assert (s.current, s.longest, s.active_today) == (0, 0, False)
