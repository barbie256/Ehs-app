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
