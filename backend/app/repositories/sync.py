"""Sync-run lifecycle and PostgreSQL session advisory-lock operations."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models.operations import SyncItemError, SyncRun

DIRECTORIST_CATALOGUE_LOCK_KEY = 499_164_875_001


class SyncRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def start(self, correlation_id: str) -> SyncRun:
        run = SyncRun(
            source_system="directorist",
            job_name="catalogue_sync",
            status="started",
            correlation_id=correlation_id,
        )
        self.session.add(run)
        self.session.flush()
        self.session.refresh(run)
        return run

    def try_lock(self) -> bool:
        return bool(
            self.session.scalar(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": DIRECTORIST_CATALOGUE_LOCK_KEY},
            )
        )

    def unlock(self) -> bool:
        return bool(
            self.session.scalar(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": DIRECTORIST_CATALOGUE_LOCK_KEY},
            )
        )

    def item_error(
        self, run_id: UUID, external_id: str, error_code: str, field_summary: str
    ) -> None:
        self.session.add(
            SyncItemError(
                sync_run_id=run_id,
                external_entity_type="listing",
                external_id=external_id[:100],
                error_code=error_code[:50],
                field_summary=field_summary[:200],
            )
        )

    def finish(self, run: SyncRun, status: str, **counts: int) -> None:
        run.status = status
        run.completed_at = datetime.now(UTC)
        for name, value in counts.items():
            setattr(run, name, value)
        self.session.flush()

    def fail(self, run: SyncRun, code: str, summary: str, **counts: int) -> None:
        run.error_code = code[:50]
        run.error_summary = summary[:500]
        self.finish(run, "failed", **counts)
