"""Synchronization, audit, and operational alert models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started','succeeded','partial','failed','skipped')", name="sync_status"
        ),
        CheckConstraint(
            "pages_requested >= 0 AND items_received >= 0 AND items_inserted >= 0 "
            "AND items_updated >= 0 AND items_unchanged >= 0 AND items_archived >= 0 "
            "AND items_pending_mapping >= 0 AND items_failed >= 0",
            name="sync_counters_nonnegative",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at", name="sync_completion_order"
        ),
        Index("ix_sync_runs_source_started", "source_system", "started_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    source_system: Mapped[str] = mapped_column(String(30))
    job_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pages_requested: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    items_received: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    items_inserted: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    items_updated: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    items_unchanged: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    items_archived: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    items_pending_mapping: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    items_failed: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_summary: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(100), index=True)


class SyncItemError(Base):
    __tablename__ = "sync_item_errors"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_runs.id", ondelete="CASCADE"), index=True
    )
    external_entity_type: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(100), index=True)
    error_code: Mapped[str] = mapped_column(String(50))
    field_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    actor_type: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[str | None] = mapped_column(String(100))
    safe_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    correlation_id: Mapped[str] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class SystemAlert(Base):
    __tablename__ = "system_alerts"
    __table_args__ = (
        CheckConstraint("severity IN ('info','warning','error','critical')", name="alert_severity"),
        CheckConstraint("status IN ('open','acknowledged','resolved')", name="alert_status"),
        CheckConstraint("occurrence_count > 0", name="alert_occurrence_positive"),
        Index(
            "uq_system_alerts_open_incident",
            "service",
            "incident_key",
            unique=True,
            postgresql_where=text("status IN ('open','acknowledged')"),
        ),
        Index("ix_system_alerts_status_last_seen", "status", "last_seen_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    service: Mapped[str] = mapped_column(String(100))
    alert_type: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'open'"))
    incident_key: Mapped[str] = mapped_column(String(200))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    occurrence_count: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    safe_details: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
