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
