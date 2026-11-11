"""HTTP adapter: translates requests into application use cases and renders templates."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.application.practice_service import PlanFilter, ProblemWork
from app.domain.errors import DomainError
from app.domain.practice.problem import LANGUAGES
from app.domain.practice.value_objects import Status
from app.interfaces.web.auth import client_id, password_matches, safe_next

TEMPLATES = Jinja2Templates(directory=Path(__file__).with_name("templates"))
router = APIRouter()


def rating_class(rating: int) -> str:
    """Codeforces rank colours."""
    for limit, cls in ((1200, "newbie"), (1400, "pupil"), (1600, "specialist"), (1900, "expert"), (2100, "cm")):
        if rating < limit:
            return cls
    return "master"


STATIC_DIR = Path(__file__).with_name("static")
ASSET_VERSION = hashlib.sha256(
    b"".join(f.read_bytes() for f in sorted(STATIC_DIR.iterdir()) if f.is_file())
).hexdigest()[:10]

TEMPLATES.env.globals.update(
    rating_class=rating_class, Status=Status, LANGUAGES=LANGUAGES, asset_version=ASSET_VERSION
)
TEMPLATES.env.filters["nice_date"] = lambda d: d.strftime("%a, %b %-d %Y") if d else ""
TEMPLATES.env.filters["short_date"] = lambda d: d.strftime("%b %-d") if d else ""


def time_ago(moment: datetime | None) -> str:
    if moment is None:
        return "never"
    seconds = int((datetime.now(timezone.utc) - moment).total_seconds())
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            n = seconds // size
            return f"{n} {unit}{'' if n == 1 else 's'} ago"
    return "just now"


TEMPLATES.env.filters["ago"] = time_ago


def render(request: Request, name: str, status_code: int = 200, **ctx: object) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, name, ctx, status_code=status_code)


def _int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError as exc:
        raise DomainError(f"'{value}' is not a whole number") from exc


def _status(value: str) -> Status:
    try:
        return Status(value)
    except ValueError as exc:
        raise DomainError(f"Unknown status '{value}'") from exc


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DomainError(f"'{value}' is not a date") from exc


# --- auth -------------------------------------------------------------------
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if request.session.get("auth"):
        return RedirectResponse(safe_next(next), status_code=303)
    return render(request, "login.html", next=safe_next(next), error=None)


@router.post("/login")
async def login(
    request: Request,
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/",
):
    throttle = request.app.state.throttle
    settings = request.app.state.settings
    client = client_id(request, settings.client_ip_header, settings.trusted_proxies)
    if throttle.blocked(client):
        return render(request, "login.html", 429, next=safe_next(next),
                      error="Too many attempts. Try again in 15 minutes.")
    if not password_matches(password, request.app.state.settings.app_password):
        throttle.fail(client)
        await asyncio.sleep(0.5)
        return render(request, "login.html", 401, next=safe_next(next), error="Wrong password.")
    throttle.reset(client)
    request.session.clear()
    request.session["auth"] = True
    return RedirectResponse(safe_next(next), status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/healthz")
def healthz(request: Request):
    with request.app.state.engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return JSONResponse({"status": "ok"})


# --- dashboard --------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return render(request, "dashboard.html", d=request.app.state.dashboard.run(), nav="dashboard")


# --- plan & problems --------------------------------------------------------
@router.get("/plan", response_class=HTMLResponse)
def plan(request: Request, status: str = "", topic: str = "", day: str = ""):
    practice = request.app.state.practice
    everything = practice.plan()
    flt = PlanFilter(
        status=Status(status) if status in {s.value for s in Status} else None,
        topic_family=topic or None,
        day=_int(day) or None,
    )
    shown = [p for p in everything if flt.matches(p)]
    days: dict[int, list] = {}
    for p in shown:
        days.setdefault(p.day, []).append(p)
    totals: dict[int, tuple[int, int]] = {}
    for p in everything:
        done, total = totals.get(p.day, (0, 0))
        totals[p.day] = (done + p.is_done, total + 1)
    families = sorted({p.topic.family for p in everything})
    return render(
        request, "plan.html", nav="plan", days=days, totals=totals, families=families,
        flt=flt, filtered=any((flt.status, flt.topic_family, flt.day)),
        shown=len(shown), all_days=sorted(totals),
    )


@router.get("/problems/{code}", response_class=HTMLResponse)
def problem_page(request: Request, code: str, saved: str = ""):
    practice = request.app.state.practice
    problem = practice.problem(code)
    prev, nxt = practice.neighbours(code)
    return render(request, "problem.html", nav="plan", p=problem, prev=prev, nxt=nxt,
                  saved=saved == "1", today=request.app.state.clock())


@router.post("/problems/{code}/status")
def change_status(
    request: Request,
    code: str,
    status: Annotated[str, Form()],
    next: Annotated[str, Form()] = "",
):
    problem = request.app.state.practice.set_status(code, _status(status))
    return RedirectResponse(safe_next(next or f"/problems/{problem.code}"), status_code=303)


@router.post("/problems/{code}/work")
def save_work(
    request: Request,
    code: str,
    notes: Annotated[str, Form()] = "",
    solution: Annotated[str, Form()] = "",
    language: Annotated[str, Form()] = "python",
    minutes: Annotated[str, Form()] = "0",
    solved_on: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "",
):
    work = ProblemWork(
        notes=notes, solution=solution, language=language,
        minutes=_int(minutes), solved_on=_date(solved_on),
        status=_status(status) if status else None,
    )
    problem = request.app.state.practice.save_work(code, work)
    return RedirectResponse(f"/problems/{problem.code}?saved=1", status_code=303)


# --- journal ----------------------------------------------------------------
@router.get("/journal", response_class=HTMLResponse)
def journal(request: Request, day: str = "", saved: str = ""):
    journal_svc = request.app.state.journal
    today = journal_svc.today()
    selected = min(_date(day) or today, today)
    history = journal_svc.history()
    solved = request.app.state.practice.solved_between([e.day for e in history] + [selected])
    return render(
        request, "journal.html", nav="journal", entry=journal_svc.entry(selected),
        selected=selected, today=today, history=history, solved=solved, saved=saved == "1",
        minutes_total=sum(e.minutes for e in history),
    )


@router.post("/journal")
def write_journal(
    request: Request,
    day: Annotated[str, Form()],
    learned: Annotated[str, Form()] = "",
    minutes: Annotated[str, Form()] = "0",
    next: Annotated[str, Form()] = "",
):
    entry_day = _date(day) or request.app.state.clock()
    request.app.state.journal.write(entry_day, learned, _int(minutes))
    return RedirectResponse(safe_next(next or f"/journal?day={entry_day}&saved=1"), status_code=303)


# --- Codeforces sync -------------------------------------------------------
@router.post("/sync/connect")
def sync_connect(request: Request, handle: Annotated[str, Form()] = ""):
    request.app.state.sync.connect(handle)
    return RedirectResponse("/#sync", status_code=303)


@router.post("/sync")
def sync_now(request: Request):
    request.app.state.sync.sync()
    return RedirectResponse("/#sync", status_code=303)


@router.post("/sync/disconnect")
def sync_disconnect(request: Request):
    request.app.state.sync.disconnect()
    return RedirectResponse("/#sync", status_code=303)
