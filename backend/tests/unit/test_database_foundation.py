"""Database safety and metadata contract tests without a connection."""

import pytest

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.session import (
    DatabaseSafetyError,
    redact_database_url,
    validate_development_url,
    validate_test_url,
)

EXPECTED_TABLES = {
    "users",
    "roles",
    "user_roles",
    "marketplaces",
    "categories",
    "locations",
    "vendors",
    "source_taxonomy_mappings",
    "listings",
    "listing_categories",
    "listing_locations",
    "listing_media",
    "listing_contacts",
    "listing_source_payloads",
    "sync_runs",
    "sync_item_errors",
    "audit_logs",
    "system_alerts",
}


def test_metadata_contains_exact_gate_3b_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_table_has_named_primary_key() -> None:
    assert all(
        table.primary_key.name == f"pk_{table.name}" for table in Base.metadata.tables.values()
    )


def test_all_constraints_and_indexes_are_named() -> None:
    for table in Base.metadata.tables.values():
        assert all(constraint.name for constraint in table.constraints)
        assert all(index.name for index in table.indexes)


@pytest.mark.parametrize("name", ["uq_users_email_active", "uq_users_phone_active"])
def test_active_user_reuse_indexes_are_partial(name: str) -> None:
    index = next(index for index in Base.metadata.tables["users"].indexes if index.name == name)
    assert index.unique
    assert "deleted_at IS NULL" in str(index.dialect_options["postgresql"]["where"])


@pytest.mark.parametrize("table_name", ["listing_categories", "listing_locations"])
def test_primary_relation_index_is_partial_unique(table_name: str) -> None:
    index = next(
        index
        for index in Base.metadata.tables[table_name].indexes
        if "primary" in (index.name or "")
    )
    assert index.unique
    assert str(index.dialect_options["postgresql"]["where"]) == "is_primary"


def test_open_alert_identity_includes_acknowledged() -> None:
    index = next(index for index in Base.metadata.tables["system_alerts"].indexes if index.unique)
    predicate = str(index.dialect_options["postgresql"]["where"])
    assert "open" in predicate and "acknowledged" in predicate


def test_latest_payload_is_one_to_one_primary_key() -> None:
    table = Base.metadata.tables["listing_source_payloads"]
    assert [column.name for column in table.primary_key.columns] == ["listing_id"]


def test_no_polymorphic_external_entities_table() -> None:
    assert "external_entities" not in Base.metadata.tables


def test_local_url_guards_accept_exact_dedicated_urls() -> None:
    development = "postgresql+psycopg://ehs_mall_local:x@127.0.0.1:5432/ehs_mall_dev"
    test = "postgresql+psycopg://ehs_mall_local:x@localhost:5432/ehs_mall_test"
    assert validate_development_url(development).database == "ehs_mall_dev"
    assert validate_test_url(test, development_url=development).database == "ehs_mall_test"


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "postgresql+psycopg://ehs_mall_local:x@db.neon.tech/ehs_mall_test",
        "postgresql+psycopg://wrong:x@localhost/ehs_mall_test",
        "postgresql+psycopg://ehs_mall_local:x@localhost/wrong",
    ],
)
def test_test_url_guard_fails_closed(url: str | None) -> None:
    with pytest.raises(DatabaseSafetyError):
        validate_test_url(url)


def test_database_url_redaction() -> None:
    safe = redact_database_url("postgresql+psycopg://user:very-secret@localhost/db")
    assert "very-secret" not in safe
    assert "***" in safe
