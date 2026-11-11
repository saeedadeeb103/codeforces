from datetime import date

import pytest

from app.domain.errors import DomainError
from app.domain.practice.value_objects import ProblemCode, Rating, Status, Topic
from tests.fakes import make_problem

TODAY = date(2026, 11, 11)


@pytest.mark.parametrize(
    "raw, contest, index, url",
    [
        ("4A", 4, "A", "https://codeforces.com/problemset/problem/4/A"),
        ("1249b1", 1249, "B1", "https://codeforces.com/problemset/problem/1249/B1"),
        (" 1526C1 ", 1526, "C1", "https://codeforces.com/problemset/problem/1526/C1"),
    ],
)
def test_problem_code_parses_contest_and_index(raw, contest, index, url):
    code = ProblemCode(raw)
    assert (code.contest_id, code.index, code.url) == (contest, index, url)


@pytest.mark.parametrize("raw", ["", "A4", "0A", "12", "4AA", "4/A", "4A12"])
def test_problem_code_rejects_garbage(raw):
    with pytest.raises(DomainError):
        ProblemCode(raw)


@pytest.mark.parametrize("value", [799, 850, 3600])
def test_rating_must_be_a_codeforces_rating(value):
    with pytest.raises(DomainError):
        Rating(value)


def test_topic_family_groups_subtopics():
    assert Topic("Graphs / BFS + DP").family == "Graphs"
    assert Topic("  Two   pointers ").name == "Two pointers"


def test_solving_sets_solved_date_and_reopening_clears_it():
    p = make_problem()
    p.change_status(Status.SOLVED, TODAY)
    assert p.is_done and p.solved_on == TODAY

    p.change_status(Status.TODO, TODAY)
    assert not p.is_done and p.solved_on is None


def test_moving_between_done_states_keeps_original_solved_date():
    p = make_problem()
    p.change_status(Status.SOLVED, date(2026, 11, 1))
    p.change_status(Status.REVIEW, TODAY)
    assert p.status is Status.REVIEW and p.solved_on == date(2026, 11, 1)


def test_attempted_is_not_done():
    p = make_problem()
    p.change_status(Status.ATTEMPTED, TODAY)
    assert not p.is_done and p.solved_on is None


def test_solved_date_rules():
    p = make_problem()
    with pytest.raises(DomainError):
        p.change_solved_date(TODAY, TODAY)  # not solved yet
    p.change_status(Status.SOLVED, TODAY)
    with pytest.raises(DomainError):
        p.change_solved_date(date(2026, 11, 12), TODAY)  # future
    p.change_solved_date(date(2026, 11, 3), TODAY)
    assert p.solved_on == date(2026, 11, 3)


def test_invariant_solved_date_iff_done():
    with pytest.raises(DomainError):
        make_problem(status=Status.SOLVED)
    with pytest.raises(DomainError):
        make_problem(solved_on=TODAY)


def test_work_validation():
    p = make_problem()
    p.record_learning("  use prefix sums  ")
    p.attach_solution("print(1)\n\n", "python")
    p.log_time(25)
    assert (p.notes, p.solution, p.time_spent_minutes) == ("use prefix sums", "print(1)", 25)
    with pytest.raises(DomainError):
        p.attach_solution("x", "cobol")
    with pytest.raises(DomainError):
        p.log_time(-1)


@pytest.mark.parametrize("value, band", [(800, "Easy"), (1100, "Easy"), (1200, "Medium"), (1500, "Medium"), (1600, "Hard"), (2100, "Hard")])
def test_rating_difficulty_band(value, band):
    assert Rating(value).difficulty == band
