"""One-shot taxonomy curation job fail-closed boundaries."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.db.readiness import SynchronizationReadiness
from app.jobs import apply_initial_taxonomy_mappings as job
from app.services.taxonomy_curation import CurationCounts, TaxonomyCurationError


def safe_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "development",
        "DATABASE_URL": "postgresql+psycopg://ehs_mall_local:x@localhost/ehs_mall_dev",
        "TEST_DATABASE_URL": "postgresql+psycopg://ehs_mall_local:y@localhost/ehs_mall_test",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize("environment", ["test", "staging", "production"])
def test_unsafe_environment_fails_before_engine(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    settings = safe_settings()
    object.__setattr__(settings, "app_env", environment)
    monkeypatch.setattr(job, "get_settings", lambda: settings)
    monkeypatch.setattr(
        job,
        "create_database_engine",
        lambda _url: pytest.fail("engine must not be created"),
    )
    assert job.run() == job.UNSAFE_CONFIGURATION


def test_missing_or_same_test_url_is_rejected_before_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = safe_settings()
    object.__setattr__(settings, "test_database_url", None)
    monkeypatch.setattr(job, "get_settings", lambda: settings)
    monkeypatch.setattr(
        job,
        "create_database_engine",
        lambda _url: pytest.fail("engine must not be created"),
    )
    assert job.run() == job.UNSAFE_CONFIGURATION


def test_readiness_failure_precedes_session_and_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = SimpleNamespace(dispose=lambda: None)
    monkeypatch.setattr(job, "get_settings", safe_settings)
    monkeypatch.setattr(job, "create_database_engine", lambda _url: engine)
    monkeypatch.setattr(
        job,
        "synchronization_readiness",
        lambda *_args, **_kwargs: SynchronizationReadiness(
            "incomplete", "0004_sync_and_audit", "0004_sync_and_audit", ("locations",)
        ),
    )
    monkeypatch.setattr(job, "Session", lambda _engine: pytest.fail("no session allowed"))
    assert job.run() == job.DATABASE_NOT_READY


def test_success_commits_once_and_reports_only_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock()
    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    monkeypatch.setattr(job, "get_settings", safe_settings)
    monkeypatch.setattr(job, "create_database_engine", lambda _url: engine)
    monkeypatch.setattr(
        job,
        "synchronization_readiness",
        lambda *_args, **_kwargs: SynchronizationReadiness(
            "current", "0004_sync_and_audit", "0004_sync_and_audit", ()
        ),
    )
    monkeypatch.setattr(job, "Session", lambda _engine: session_context)
    monkeypatch.setattr(
        job,
        "apply_initial_taxonomy_mappings",
        lambda _session: CurationCounts(12, 12, 0, 11, 1),
    )
    assert job.run() == job.SUCCESS
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()


def test_decision_mismatch_rolls_back_without_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock()
    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    monkeypatch.setattr(job, "get_settings", safe_settings)
    monkeypatch.setattr(job, "create_database_engine", lambda _url: engine)
    monkeypatch.setattr(
        job,
        "synchronization_readiness",
        lambda *_args, **_kwargs: SynchronizationReadiness(
            "current", "0004_sync_and_audit", "0004_sync_and_audit", ()
        ),
    )
    monkeypatch.setattr(job, "Session", lambda _engine: session_context)

    def reject(_session: object) -> CurationCounts:
        raise TaxonomyCurationError("controlled")

    monkeypatch.setattr(job, "apply_initial_taxonomy_mappings", reject)
    assert job.run() == job.DECISION_MISMATCH
    session.rollback.assert_called_once_with()
    session.commit.assert_not_called()
