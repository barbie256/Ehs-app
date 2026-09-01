# EHS Mall backend — Gate 3B database foundation

This backend uses synchronous SQLAlchemy 2.x with Psycopg, PostgreSQL UUIDs and
timezone-aware timestamps. Alembic is the only schema creation and mutation mechanism:
application startup never calls `create_all()` and never upgrades automatically.

The four revisions are `0001_identity_foundation`, `0002_canonical_taxonomy`,
`0003_sources_and_catalogue`, and `0004_sync_and_audit`. The explicit seed command is
`python -m app.services.taxonomy_seed`. It creates four marketplaces, 44 scoped categories,
and five roles, but no users, vendors, or listings. Reruns preserve administrator-edited
display names.

Source identity is typed: listings and vendors carry `source_system` and `external_id`,
while `source_taxonomy_mappings` owns directory/category/location identities. There is no
polymorphic linked-target UUID registry. URL syntax, HTTPS, allowed hosts, and URL lengths
remain application validation concerns. Category/location depth (maximum three), cycles,
and same-marketplace parent validation remain documented service responsibilities; direct
self-parenting is prevented by database checks.

See `docs/development-setup.md` for safe local commands. No command writes to WordPress.

## Gate 4 read-only Directorist adapter

`app.integrations.directorist` contains strict v1 source schemas, a pure normalized mapper,
and an asynchronous client exposing only listing pages, individual listings, directories,
categories, and locations. It can issue only GETs to fixed v1 paths. Redirects,
non-JSON/oversized responses, unsafe pagination, and schema failures are rejected;
connection, timeout, and selected transient 5xx retries are narrowly bounded.

Tests use HTTPX mock transports and the reviewed synthetic fixture only. Gate 4 has no live
smoke test, website write, persistence, or synchronization behavior. Taxonomy resolution is
injected through a protocol; unknown categories remain pending and incompatible marketplace
mappings fail safely. Currency remains null, `price=0` is preserved without interpretation,
hidden contacts are discarded, and visible contacts never appear in summaries. Upstream
HTML is sanitized with a small allowlist before normalization.

## Gate 5A offline-testable catalogue synchronization

`python -m app.jobs.sync_directorist` is the explicit one-shot entry point. It validates
that `DATABASE_URL` is the dedicated local `ehs_mall_dev` database before connecting, then
uses one database connection for the complete job and its PostgreSQL session advisory lock.
The command performs real read-only Directorist GET requests when invoked, so it must not be
run without separate approval for the configured source. Gate 5A verification uses fakes,
HTTPX mock transports, and only the guarded `ehs_mall_test` database; it makes no live HTTP
request.

The job exit codes are `0` succeeded, `2` lock-held/skipped, `3` partial, `10`
configuration failure, `11` database/migration failure, `12` upstream failure, and `13`
unexpected controlled failure. A page commits atomically, invalid members use savepoints
and safe error codes, and only a complete failure-free traversal marks unseen Directorist
listings unavailable. The stable advisory-lock key is `499164875001`. Taxonomy discovery
updates name snapshots while preserving pending, approved, or rejected decisions; it never
matches names automatically.

The existing `last_synced_at` column is the observation marker. Changed normalized records
replace only source-owned relations and the latest sanitized payload; unchanged records
only refresh observation state. Hidden contacts are omitted, hidden coordinates are removed
from the stored payload, and only HTTPS media references are retained.
