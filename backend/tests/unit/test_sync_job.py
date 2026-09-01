"""One-shot job exits safely before I/O on configuration rejection."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.db.readiness import SYNCHRONIZATION_TABLES, SynchronizationReadiness
from app.db.session import DatabaseSafetyError
from app.jobs import sync_directorist


def safe_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "development",
        "DATABASE_URL": "postgresql+psycopg://ehs_mall_local:x@localhost/ehs_mall_dev",
        "DIRECTORIST_BASE_URL": "https://ehsmall.com",
        "DIRECTORIST_API_VERSION": "v1",
    }
    values.update(overrides)
    return Settings(**values)


def test_job_configuration_failure_exit_code(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def reject(_: str) -> None:
        raise DatabaseSafetyError("safe rejection")

    monkeypatch.setattr(sync_directorist, "validate_development_url", reject)
    assert asyncio.run(sync_directorist._run()) == 10


@pytest.mark.parametrize("environment", ["test", "staging", "production"])
def test_job_rejects_non_development_before_engine_creation(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    settings = safe_settings()
    object.__setattr__(settings, "app_env", environment)
    monkeypatch.setattr(sync_directorist, "get_settings", lambda: settings)
    monkeypatch.setattr(
        sync_directorist,
        "create_database_engine",
        lambda _: pytest.fail("engine creation must not occur"),
    )
    assert asyncio.run(sync_directorist._run()) == 10


@pytest.mark.parametrize(
    "source",
    [
        "http://ehsmall.com",
        "https://api.ehsmall.com",
        "https://ehsmall.com.example",
        "https://not-ehsmall.com",
        "https://127.0.0.1",
        "https://user:password@ehsmall.com",
        "https://ehsmall.com:444",
    ],
)
def test_job_rejects_unapproved_source_before_engine_creation(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    settings = safe_settings()
    object.__setattr__(settings, "directorist_base_url", source)
    monkeypatch.setattr(sync_directorist, "get_settings", lambda: settings)
    monkeypatch.setattr(
        sync_directorist,
        "create_database_engine",
        lambda _: pytest.fail("engine creation must not occur"),
    )
    assert asyncio.run(sync_directorist._run()) == 10


def test_job_boundary_accepts_exact_approved_configuration() -> None:
    sync_directorist._validate_job_boundary(safe_settings())
    sync_directorist._validate_job_boundary(
        safe_settings(DIRECTORIST_BASE_URL="https://ehsmall.com:443")
    )


def test_incomplete_inventory_stops_before_session_client_or_lock(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    engine = SimpleNamespace(dispose=lambda: None)
    monkeypatch.setattr(sync_directorist, "get_settings", safe_settings)
    monkeypatch.setattr(sync_directorist, "create_database_engine", lambda _: engine)
    monkeypatch.setattr(
        sync_directorist,
        "synchronization_readiness",
        lambda *_args, **_kwargs: SynchronizationReadiness(
            "incomplete", "0004_sync_and_audit", "0004_sync_and_audit", ("listings",)
        ),
    )
    monkeypatch.setattr(
        sync_directorist,
        "Session",
        lambda **_kwargs: pytest.fail("session creation must not occur"),
    )
    monkeypatch.setattr(
        sync_directorist,
        "DirectoristClient",
        lambda **_kwargs: pytest.fail("HTTP client creation must not occur"),
    )
    assert asyncio.run(sync_directorist._run()) == 11
    assert caplog.messages == ["catalogue sync database readiness rejected"]
    assert "listings" not in caplog.text
    assert "postgresql" not in caplog.text


def test_approved_configuration_preserves_successful_job_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = MagicMock()
    connection = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    client_context = MagicMock()
    source = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=source)
    client_context.__aexit__ = AsyncMock(return_value=False)
    service = MagicMock()
    service.run = AsyncMock(
        return_value=SimpleNamespace(
            status="succeeded",
            exit_code=0,
            counts=SimpleNamespace(items_received=23, items_failed=0),
        )
    )
    monkeypatch.setattr(sync_directorist, "get_settings", safe_settings)
    monkeypatch.setattr(sync_directorist, "create_database_engine", lambda _: engine)
    monkeypatch.setattr(
        sync_directorist,
        "synchronization_readiness",
        lambda *_args, **_kwargs: SynchronizationReadiness(
            "current", "0004_sync_and_audit", "0004_sync_and_audit", ()
        ),
    )
    monkeypatch.setattr(sync_directorist, "Session", lambda **_kwargs: session_context)
    monkeypatch.setattr(sync_directorist, "DirectoristClient", lambda **_kwargs: client_context)
    monkeypatch.setattr(sync_directorist, "CatalogueSyncService", lambda *_args, **_kwargs: service)

    assert asyncio.run(sync_directorist._run()) == 0
    service.run.assert_awaited_once()


def test_synchronization_inventory_is_frozen_and_complete() -> None:
    assert {
        "alembic_version",
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
    } == SYNCHRONIZATION_TABLES
