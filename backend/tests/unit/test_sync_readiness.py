"""Non-mutating synchronization schema-readiness checks."""

from typing import cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Engine

from app.db import readiness


def readiness_engine(monkeypatch: pytest.MonkeyPatch, tables: set[str], revision: str) -> Engine:
    inspector = MagicMock()
    inspector.get_table_names.return_value = sorted(tables)
    monkeypatch.setattr(readiness, "inspect", lambda _connection: inspector)

    result = MagicMock()
    result.scalar_one_or_none.return_value = revision
    connection = MagicMock()
    connection.execute.return_value = result
    engine = MagicMock(spec=Engine)
    engine.connect.return_value.__enter__.return_value = connection
    return engine


def test_complete_inventory_at_head_is_current(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = readiness_engine(
        monkeypatch, set(readiness.SYNCHRONIZATION_TABLES), "0004_sync_and_audit"
    )
    result = readiness.synchronization_readiness(engine)
    assert result.status == "current"
    assert result.missing_tables == ()


def test_missing_table_fails_even_when_revision_claims_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = set(readiness.SYNCHRONIZATION_TABLES) - {"listings"}
    engine = readiness_engine(monkeypatch, tables, "0004_sync_and_audit")
    result = readiness.synchronization_readiness(engine)
    assert result.status == "incomplete"
    assert result.missing_tables == ("listings",)


def test_readiness_only_reads_version_and_never_repairs_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = set(readiness.SYNCHRONIZATION_TABLES) - {"listing_media"}
    engine = readiness_engine(monkeypatch, tables, "0004_sync_and_audit")
    result = readiness.synchronization_readiness(engine)
    connection = cast(MagicMock, engine.connect).return_value.__enter__.return_value
    assert result.status == "incomplete"
    assert connection.execute.call_count == 1
    assert str(connection.execute.call_args.args[0]) == "SELECT version_num FROM alembic_version"
