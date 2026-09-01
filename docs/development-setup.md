# Gate 3B local development setup

PostgreSQL runs locally at `127.0.0.1:5432` with dedicated role `ehs_mall_local`.
Development uses `ehs_mall_dev`; destructive migration tests use only `ehs_mall_test`.

## Windows PowerShell

From the repository root:

```powershell
backend/.venv/Scripts/python.exe -m pip install -e "backend[dev]"
backend/.venv/Scripts/python.exe -m ruff format --check backend
backend/.venv/Scripts/python.exe -m ruff check backend
backend/.venv/Scripts/python.exe -m mypy backend/app backend/tests
backend/.venv/Scripts/python.exe -m pytest backend/tests
backend/.venv/Scripts/python.exe -m pip check
backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini history
backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini heads
```

To run the local foundation from `backend/`:

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Copy `backend/.env.example` to ignored `backend/.env` and privately replace both password
placeholders with the dedicated role password. Never use the PostgreSQL administrator
password. Percent-encode reserved password characters (`@` as `%40`, `:` as `%3A`, `/` as
`%2F`, `#` as `%23`, `%` as `%25`). Never commit `.env`.

Load the selected private URL into `ALEMBIC_DATABASE_URL` without printing it before using
`alembic upgrade head`. Run `python -m app.services.taxonomy_seed` only with the guarded
development URL.

Database tests fail closed unless `TEST_DATABASE_URL` names exactly `ehs_mall_test`, uses a
local host and role `ehs_mall_local`, and differs from `DATABASE_URL`. They rehearse
base→head→base→head. Never point tests at development, production, Neon, MPU, or unrelated
databases. The development database is upgraded once and is not downgraded after success.

Alembic owns schema changes. Import/startup is non-mutating and never runs migrations
automatically. This project performs no production WordPress writes.

## Offline Directorist adapter tests

Gate 4 uses only `backend/tests/fixtures/directorist_listing_v1.json`, copied byte-for-byte
from the approved documentation fixture with a frozen SHA-256 assertion. HTTP behavior is
exercised through `httpx.MockTransport`; no test contacts a live host.

The read-only client supports listing pages, individual listings, directories, categories,
and locations. It has explicit timeouts, bounded transient retries, response-size and JSON
checks, safe pagination, redirect rejection, and no authorization/cookie configuration.
Taxonomy mapping is injected rather than hard-coded. Currency stays unknown, zero price is
uninterpreted, and contact visibility is enforced before public projection. No Gate 4
command writes to WordPress or PostgreSQL.

## Gate 5A synchronization verification

The automated Gate 5A suite uses fake Directorist collections and the frozen synthetic
fixture. It exercises transactional listing persistence only in `ehs_mall_test`, after the
same exact database/role/local-host/different-URL guard used by the migration tests:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests
```

The installed one-shot entry point is:

```powershell
cd backend
.venv/Scripts/python.exe -m app.jobs.sync_directorist
```

That command uses `ehs_mall_dev` and performs read-only network GETs against the configured
Directorist host. Do not invoke it without explicit approval for both that database and
source host. It never selects `TEST_DATABASE_URL`, never falls back between databases, and
does not create or migrate schema. Run Alembic separately before an approved synchronization.

Exit codes are: `0` success, `2` overlap skipped, `3` partial item failures, `10` unsafe or
invalid configuration, `11` database failure, `12` Directorist failure, and `13` another
controlled failure. Partial and failed runs never archive unseen listings.

## Offline verification of the read-only probe

Gate 5B-R1 adds a database-free probe module intended for a separately approved live dry
run. Its future command is:

```powershell
cd backend
.venv/Scripts/python.exe -u -m app.jobs.probe_directorist_readonly
```

Do not run that command until Gate 5B-R2 explicitly authorizes live access. The command is
fixed to four HTTPS GET attempts against the approved Directorist v1 paths on `ehsmall.com`.
It has no CLI configuration, database access, persistence, retries, redirects, credentials,
cookies, extra pagination, or record follow-up. The total deadline is 45 seconds.

Safe flushed JSON-line events distinguish start, attempt, successful validated response,
controlled failure stage, and final aggregate. Only aggregate counts, byte sizes, durations,
approved pagination totals, invariant booleans, and controlled codes are emitted. Exit code
`0` means all four endpoints passed, `12` means a controlled upstream or validation failure,
and `13` means an internal or cleanup failure.

Run its offline scenarios with:

```powershell
backend/.venv/Scripts/python.exe -m pytest `
  backend/tests/integration/test_directorist_probe.py `
  backend/tests/unit/test_directorist_probe_safety.py
```

These tests use only `httpx.MockTransport` and synthetic fixtures.
