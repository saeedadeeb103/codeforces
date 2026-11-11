from datetime import date
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, Settings
from app.infrastructure.db import normalize_database_url
from app.interfaces.web.auth import is_public, safe_next
from app.interfaces.web.routes import router
from app.main import create_app

PASSWORD = "correct horse battery staple"
TODAY = date(2026, 11, 11)


def _settings(tmp_path) -> Settings:
    return Settings(
        app_password=PASSWORD,
        secret_key="x" * 40,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        timezone=ZoneInfo("Europe/Berlin"),
        production=False,
        cf_sync_minutes=0,
    )


@pytest.fixture
def app(tmp_path):
    return create_app(_settings(tmp_path), clock=lambda: TODAY)


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def authed(client):
    r = client.post("/login", data={"password": PASSWORD}, follow_redirects=False)
    assert r.status_code == 303
    return client


# --- auth --------------------------------------------------------------------
def test_every_route_requires_login(client):
    checked = 0
    for route in router.routes:  # every page and action the app serves
        methods = getattr(route, "methods", None)
        if not methods or is_public(route.path):
            continue
        path = route.path.replace("{code}", "4A")
        for method in methods - {"HEAD"}:
            r = client.request(method, path, follow_redirects=False)
            assert r.status_code == 303, (method, path, r.status_code)
            assert r.headers["location"].startswith("/login"), (method, path)
            checked += 1
    assert checked >= 8


def test_wrong_password_is_rejected_and_throttled(client):
    for _ in range(5):
        assert client.post("/login", data={"password": "nope"}).status_code == 401
    assert client.post("/login", data={"password": PASSWORD}).status_code == 429


def test_login_redirects_back_but_never_off_site(client):
    r = client.post("/login", data={"password": PASSWORD, "next": "//evil.com"}, follow_redirects=False)
    assert r.headers["location"] == "/"
    assert client.get("/plan").status_code == 200


def test_logout_ends_session(authed):
    authed.post("/logout")
    assert authed.get("/", follow_redirects=False).status_code == 303


def test_healthz_is_public(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_safe_next():
    assert safe_next("/plan?x=1#day-2") == "/plan?x=1#day-2"
    for bad in ("https://evil.com", "//evil.com", "/\\evil.com", "", None):
        assert safe_next(bad) == "/"


# --- pages & flows -------------------------------------------------------------
def test_pages_render(authed):
    for path in ("/", "/plan", "/plan?status=todo&topic=Graphs&day=20", "/problems/1249B1", "/journal"):
        r = authed.get(path)
        assert r.status_code == 200, path
    assert "Watermelon" in authed.get("/").text
    assert "Day 1" in authed.get("/").text


def test_solve_note_code_and_progress_moves(authed, app):
    r = authed.post("/problems/4A/status", data={"status": "solved", "next": "/"}, follow_redirects=False)
    assert r.headers["location"] == "/"
    r = authed.post(
        "/problems/4A/work",
        data={"notes": "even and > 2", "solution": "w=int(input())\nprint('YES' if w%2==0 and w>2 else 'NO')",
              "language": "python", "minutes": "7", "solved_on": "2026-11-10"},
    )
    assert r.status_code == 200 and "Saved" in r.text and "even and &gt; 2" in r.text

    p = app.state.practice.problem("4A")
    assert (p.time_spent_minutes, p.solved_on) == (7, date(2026, 11, 10))
    page = authed.get("/").text
    assert "1 / 200 solved" in page


def test_status_button_saves_notes_and_code_in_one_post(authed, app):
    r = authed.post(
        "/problems/339A/work",
        data={"notes": "sort the digits", "solution": "print('+'.join(sorted(input().split('+'))))",
              "language": "python", "minutes": "4", "status": "solved"},
    )
    assert r.status_code == 200
    p = app.state.practice.problem("339A")
    assert (p.status.value, p.solved_on, p.notes, p.time_spent_minutes) == ("solved", TODAY, "sort the digits", 4)
    assert "sorted(input()" in p.solution

    # Plain save (Enter / Cmd+S) leaves the status alone; un-solving drops the date even if one is posted.
    authed.post("/problems/339A/work", data={"notes": "sort the digits!", "solved_on": "2026-11-11"})
    assert app.state.practice.problem("339A").status.value == "solved"
    authed.post("/problems/339A/work", data={"status": "todo", "solved_on": "2026-11-11"})
    p = app.state.practice.problem("339A")
    assert (p.status.value, p.solved_on) == ("todo", None)


def test_problem_page_status_buttons_are_inside_work_form(authed):
    html = authed.get("/problems/4A").text
    form = html[html.index('id="work-form"'):html.index("</form>", html.index('id="work-form"'))]
    assert form.count('name="status"') == 4
    assert form.index('class="sr-only"') < form.index('name="status"')  # Enter = plain save


def test_codeforces_connect_sync_and_disconnect(tmp_path):
    from app.domain.practice.submissions import SubmissionHistory
    from app.domain.practice.value_objects import ProblemCode
    from tests.fakes import FakeSubmissionSource

    source = FakeSubmissionSource(SubmissionHistory(
        first_accepted={ProblemCode("158A"): date(2026, 11, 3), ProblemCode("231A"): date(2026, 11, 3)},
        tried=frozenset({ProblemCode("158A"), ProblemCode("231A"), ProblemCode("1A")}),
    ))
    app = create_app(_settings(tmp_path), clock=lambda: TODAY, submission_source=source)
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD})

    assert "Connect Codeforces" in c.get("/").text
    r = c.post("/sync/connect", data={"handle": "tourist"})
    assert r.status_code == 200 and "Sync now" in r.text and "+2 solved, +1 attempted" in r.text
    assert app.state.practice.problem("158A").solved_on == date(2026, 11, 3)
    assert app.state.practice.problem("1A").status.value == "attempted"

    assert c.post("/sync/connect", data={"handle": "bad handle!"}).status_code == 400
    c.post("/sync/disconnect")
    assert "Connect Codeforces" in c.get("/").text
    assert app.state.practice.problem("158A").status.value == "solved"  # progress stays


def test_data_survives_restart(tmp_path):
    settings = _settings(tmp_path)
    c1 = TestClient(create_app(settings, clock=lambda: TODAY))
    c1.post("/login", data={"password": PASSWORD})
    c1.post("/problems/71A/status", data={"status": "review"})
    c1.post("/journal", data={"day": "2026-11-11", "learned": "abbreviations", "minutes": "40"})

    app2 = create_app(settings, clock=lambda: TODAY)  # same DB, re-seed must not wipe anything
    assert app2.state.practice.problem("71A").status.value == "review"
    assert app2.state.journal.entry(TODAY).learned == "abbreviations"
    assert len(app2.state.practice.plan()) == 200


def test_bad_input_gives_friendly_errors(authed):
    assert authed.get("/problems/nope").status_code == 400
    assert authed.get("/problems/9999Z").status_code == 404
    assert authed.post("/problems/4A/status", data={"status": "bogus"}).status_code == 400
    assert authed.post("/problems/4A/work", data={"minutes": "abc"}).status_code == 400
    assert authed.post("/journal", data={"day": "2030-01-01", "learned": "x"}).status_code == 400


# --- config ------------------------------------------------------------------
def test_config_fails_closed():
    with pytest.raises(ConfigError, match="APP_PASSWORD"):
        Settings.from_env({"SECRET_KEY": "s"})
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        Settings.from_env({"APP_PASSWORD": "p", "SECRET_KEY": "s" * 40, "RAILWAY_PROJECT_ID": "x"})
    with pytest.raises(ConfigError, match="SECRET_KEY"):
        Settings.from_env({"APP_PASSWORD": "p", "SECRET_KEY": "short", "APP_ENV": "production",
                           "DATABASE_URL": "postgresql://u:p@h/db"})
    with pytest.raises(ConfigError, match="CF_SYNC_MINUTES"):
        Settings.from_env({"APP_PASSWORD": "p", "SECRET_KEY": "s", "CF_SYNC_MINUTES": "1"})
    s = Settings.from_env({"APP_PASSWORD": "p", "SECRET_KEY": "s"})
    assert s.database_url.startswith("sqlite") and str(s.timezone) == "Europe/Berlin"
    assert s.cf_sync_minutes == 30


def test_database_url_normalisation():
    assert normalize_database_url("postgres://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalize_database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"
