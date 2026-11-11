# CF Tracker

A personal, password-protected tracker for the **Codeforces 200 Practice Plan**: 200 problems over 25 days (8 a day, rated 800 → 2100).

- **Dashboard:** overall progress bar, a bar for each of the 25 days, streaks, solved-today vs. the target of 8, a 26-week activity grid, and progress by topic and by rating.
- **Plan:** every problem grouped by day, with one-click "solved" checkboxes and filters for status, topic and day.
- **Problem page:** status (To do / Attempted / Solved / Review again), *what I learned*, your solution code, time spent, and the solved date.
- **Journal:** one entry per day for what you learned and the minutes you coded. Each entry is linked to the problems you solved that day.
- **Codeforces sync:** connect your handle on the dashboard. Every `CF_SYNC_MINUTES` (default 30) the app reads your submissions from the public API:
  - an Accepted submission marks the problem solved, dated by your first accept in your time zone
  - submissions without an accept move a "To do" problem to "Attempted"
  - it never un-solves anything and never touches your notes or code
  - "Sync now" runs it immediately, at most once every 30 seconds

## Architecture (Domain-Driven Design)

```
app/
├── domain/                  # pure Python: no FastAPI, no SQLAlchemy
│   ├── practice/            # Practice context
│   │   ├── problem.py       #   Problem aggregate (status transitions, invariants)
│   │   ├── value_objects.py #   ProblemCode, Rating, Topic, Status
│   │   ├── progress.py      #   domain service: progress by day / topic / rating
│   │   └── repository.py    #   repository port
│   │   └── submissions.py   #   domain service: apply Codeforces history to the plan
│   ├── journal/             # Journal context: JournalEntry + repository port
│   ├── sync/                # Sync context: SyncState (handle, last result)
│   ├── streak.py            # domain service shared by both contexts
│   └── errors.py
├── application/             # use cases: orchestrate the domain through a Unit of Work
│   ├── practice_service.py  #   set status, save work, filter plan
│   ├── journal_service.py   #   write / read journal
│   ├── dashboard.py         #   read model combining both contexts
│   ├── plan_seeding.py      #   insert missing plan problems, never overwrite progress
│   ├── sync_service.py      #   connect handle, sync (+ SubmissionSource port)
│   └── unit_of_work.py      #   port
├── infrastructure/          # adapters
│   ├── db.py                #   SQLAlchemy tables, engine, Postgres URL handling
│   ├── repositories.py      #   repository implementations (rows ↔ domain objects)
│   ├── unit_of_work.py
│   ├── codeforces.py        #   Codeforces API adapter (user.status)
│   └── seed/plan.csv        #   the 200 problems
├── interfaces/web/          # FastAPI routes, auth gate, Jinja templates, CSS/JS
├── config.py
└── main.py                  # composition root
```

Dependencies point inward only: `interfaces → application → domain`, and `infrastructure` implements the domain and application ports.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # then set APP_PASSWORD and SECRET_KEY
.venv/bin/uvicorn --factory app.main:create_app --reload
# open http://127.0.0.1:8000
```

Locally the data lives in `./cf_tracker.db` (SQLite). Set `DATABASE_URL` to use Postgres instead.

## Tests

```bash
.venv/bin/python -m pytest
```

The tests cover:

- the domain rules
- progress and streaks
- use cases, run with an in-memory Unit of Work
- that every route redirects to login when you aren't signed in
- login throttling
- data surviving a restart
- the integrity of the plan file

## Deploy to Railway

1. Push this folder to a GitHub repo.
2. In Railway, create a **New Project → Deploy from GitHub repo** and pick the repo. It builds from the `Dockerfile` (see `railway.json`).
3. In the same project, add **Database → PostgreSQL**.
4. In the app service's **Variables**, set:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference to the Postgres service) |
   | `APP_PASSWORD` | your login password (at least 12 characters; a long random one is best) |
   | `SECRET_KEY` | output of `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
   | `APP_TIMEZONE` | `Europe/Berlin` (or your zone; decides what "today" means) |
   | `CF_SYNC_MINUTES` | optional, default `30`; `0` turns the background sync off |

5. **Settings → Networking → Generate Domain** gives you the public URL.

On Railway the app refuses to start without `DATABASE_URL`, because the container disk is wiped on every deploy. It also refuses to start without an `APP_PASSWORD` of at least 12 characters, and without a `SECRET_KEY` of at least 32 characters. Logins are limited to 5 failures per IP address and 20 failures overall per 15 minutes. If someone trips the overall limit, the login page locks for 15 minutes, but browsers already logged in stay logged in. Tables are created on first boot, and the 200 problems are inserted if missing. Redeploys never overwrite your progress.

## Notes

- Schema changes: tables are created with `create_all`, which does not alter existing tables. If you later add columns, introduce Alembic migrations.
- Changing the plan: edit `app/infrastructure/seed/plan.csv`. New codes are added on the next boot, and existing rows (and your notes) are kept.
- Sync matches problems by contest id and letter. If you solved one in the parallel Div. 1 or Div. 2 contest, it has a different code there, so tick it by hand.
- Rating fix: the sheet lists `1526C1 Potions (Easy Version)` as 1600, but Codeforces rates it 1500. The seed file uses 1500.
