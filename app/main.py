"""Composition root: wires infrastructure into the application services and the web adapter.

Run locally:  uvicorn --factory app.main:create_app --reload
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.application.dashboard import DashboardQuery
from app.application.journal_service import JournalService
from app.application.plan_seeding import seed_plan
from app.application.practice_service import PracticeService
from app.application.sync_service import SubmissionSource, SyncService
from app.application.unit_of_work import Clock
from app.config import Settings
from app.domain.errors import DomainError, NotFound
from app.infrastructure.codeforces import CodeforcesApi
from app.infrastructure.db import Base, make_engine, make_session_factory
from app.infrastructure.seed.plan_loader import load_plan
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.interfaces.web.auth import LoginThrottle, RequireLogin
from app.interfaces.web.routes import STATIC_DIR, render, router, wants_json


log = logging.getLogger("cf_tracker")


async def _auto_sync(service: SyncService, every_seconds: int) -> None:
    await asyncio.sleep(5)  # let the server finish booting
    while True:
        await asyncio.to_thread(service.sync_if_connected)
        await asyncio.sleep(every_seconds)


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    submission_source: SubmissionSource | None = None,
) -> FastAPI:
    if settings is None:
        load_dotenv(override=False)  # local convenience; real env vars win
        settings = Settings.from_env()

    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    seed_plan(uow_factory, load_plan())

    tz = settings.timezone
    clock = clock or (lambda: datetime.now(tz).date())

    sync = SyncService(
        uow_factory,
        submission_source or CodeforcesApi(tz),
        now=lambda: datetime.now(timezone.utc),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = None
        if settings.cf_sync_minutes > 0:
            task = asyncio.create_task(_auto_sync(sync, settings.cf_sync_minutes * 60))
        yield
        if task:
            task.cancel()

    app = FastAPI(
        title="CF Tracker", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.clock = clock
    app.state.throttle = LoginThrottle()
    app.state.practice = PracticeService(uow_factory, clock)
    app.state.journal = JournalService(uow_factory, clock)
    app.state.dashboard = DashboardQuery(uow_factory, clock)
    app.state.sync = sync

    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Order matters: the last middleware added runs first, so the session exists before the gate.
    app.add_middleware(RequireLogin)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="cf_tracker",
        max_age=60 * 60 * 24 * 30,
        same_site="lax",
        https_only=settings.production,
    )

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        if wants_json(request):
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        return render(request, "error.html", 400, title="That didn't work", message=str(exc))

    @app.exception_handler(NotFound)
    async def not_found(request: Request, exc: NotFound):
        if wants_json(request):
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
        return render(request, "error.html", 404, title="Not found", message=str(exc))

    return app
