"""One-shot job exits safely before I/O on configuration rejection."""

import asyncio

from app.db.session import DatabaseSafetyError
from app.jobs import sync_directorist


def test_job_configuration_failure_exit_code(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def reject(_: str) -> None:
        raise DatabaseSafetyError("safe rejection")

    monkeypatch.setattr(sync_directorist, "validate_development_url", reject)
    assert asyncio.run(sync_directorist._run()) == 10
