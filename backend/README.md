# EHS Mall backend — Gate 3B database foundation

This backend uses synchronous SQLAlchemy 2.x with Psycopg, PostgreSQL UUIDs and
timezone-aware timestamps. Alembic is the only schema creation and mutation mechanism:
application startup never calls `create_all()` and never upgrades automatically.

The four revisions are `0001_identity_foundation`, `0002_canonical_taxonomy`,
`0003_sources_and_catalogue`, and `0004_sync_and_audit`. The explicit seed command is
`python -m app.services.taxonomy_seed`. It creates four marketplaces, 46 scoped categories,
the Africa → Uganda → Kampala location hierarchy, and five roles, but no users, vendors, or
listings. Reruns preserve administrator-edited display names.

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

`python -m app.jobs.sync_directorist` is the explicit one-shot entry point. It fails closed
unless `APP_ENV` is exactly `development`, the source is exactly HTTPS `ehsmall.com` on its
standard port, and `DATABASE_URL` is the dedicated local `ehs_mall_dev` database. Before
HTTP, advisory-lock acquisition, or a sync-run write, it verifies both Alembic head and a
frozen inventory of synchronization tables. It never creates or repairs tables, then uses
one database connection for the complete job and its PostgreSQL session advisory lock.
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

Directorist source checksums use version 2 of a pure canonical contract. Category, location,
media, and contact collections are ordered by stable source identity; decimals and aware
datetimes use canonical representations; and every persisted source-owned field has an
explicit inclusion or exclusion decision. Resolver decisions and database identities remain
outside the source checksum. Classification and canonical category/location relations are
re-evaluated independently, so an approved, changed, removed, or rejected mapping can update
classification without rewriting media, contacts, or the latest sanitized payload.

The first approved synchronization after this checksum change is a controlled transition:
existing version-1 checksums should update to version 2. A separately approved stability run
must then report unchanged records when source content and classification are unchanged.
Lock-release failure after an already-finalized run remains follow-up work. Public contact
display remains blocked on explicit consent and policy review.

## Initial taxonomy curation

The canonical seed adds `energy_solutions` and `building_materials` to Construction. Location
slugs are stable codes: `africa` is the root, `uganda` is its child, and `kampala` is a child
of Uganda. This is an extensible hierarchy, not a default-country rule: future African
countries and their regions or cities are added by stable code, while missing listing
locations remain missing or pending. Categories remain country-independent, and currency is
never inferred from location or defaulted to UGX.

`python -m app.jobs.apply_initial_taxonomy_mappings` is a development-only, database-only
curation command. It accepts no runtime mapping input and applies exactly the committed 12
human decisions: ten category approvals, Kampala's location approval, and rejection of the
generic Business directory. It validates the complete source ID/name inventory, active
canonical targets, marketplace ownership, and the exact Africa/Uganda/Kampala path before
changing anything; all decisions commit together or none do. Run the canonical seed first.
Rerunning an already matching decision set is unchanged.

The curation command does not reclassify listings. A separate explicitly authorized
synchronization is required afterward. Checksum stability remains unresolved, so recurring
or scheduled synchronization remains prohibited.

## Gate 5B-R1 durable read-only probe

The future observation-only command is:

```powershell
python -u -m app.jobs.probe_directorist_readonly
```

It is permanently fixed to HTTPS `ehsmall.com` and exactly four Directorist v1 GET attempts:
directories, listing categories, listing locations, then listing page 1 with `per_page=2`.
It accepts no host, URL, path, method, header, credential, cookie, or pagination arguments.
Retries are disabled, redirects are rejected, individual records and additional pages are
never followed, and the complete operation has a 90-second deadline.

The probe imports no database, repository, or synchronization code and stores nothing. It
emits flushed JSON lines for start, endpoint attempt, safe endpoint completion/failure, and
an outermost final aggregate. Events contain only counts, approved aggregate pagination
values, byte size, duration, controlled codes, and invariant results—never source records,
contacts, identifiers, URLs, headers, or exception text. Exit codes are `0` for all four
endpoints passing, `12` for a controlled upstream/validation failure, and `13` for a
controlled internal or cleanup failure.

Gate 5B-R1 tests use only `httpx.MockTransport`. Do not execute the command against the live
host without separate Gate 5B-R2 approval.

When a sampled listing fails Pydantic validation, the probe reports structural diagnostics
only: its one-based sample position, a sanitized declared-schema field path, a stable error
type, and an occurrence count. The failure event also includes safe response-byte,
collection-item, failed-item, and total-validation-error counts. Diagnostics are capped at
20 unique entries and set `diagnostics_truncated=true` when additional unique entries exist.

Field paths allow only declared schema names, numeric collection positions, underscores,
and dot separators; unexpected components become `redacted`. Error types use a bounded
code pattern and otherwise become `validation_error`. Pydantic messages, rejected inputs,
documentation URLs, exception strings, source IDs, and record values are never copied into
events. Invalid listings are never normalized, and any invalid sample keeps the probe
failed. Another live execution requires separate approval.

Pagination failures use a separate controlled diagnostic category. The failure event may
report only header-presence and integer-validity booleans, bounded parsed totals, the fixed
requested page, returned collection count, configured page bound, and one allowlisted reason
code. Raw header strings and names are never emitted. The client keeps reported-page-limit
enforcement enabled by default. The probe alone disables that metadata comparison while
retaining `max_pages=1` as its request-page bound; it still performs four attempts and never
requests another page. Missing, malformed, negative, contradictory, or undersized metadata
continues to fail.
