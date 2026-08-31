"""Synchronization and audit operations with revision-owned immutable DDL."""

from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_sync_and_audit"
down_revision = "0003_sources_and_catalogue"
branch_labels = None
depends_on = None


def uuid_id() -> sa.Column[object]:
    return cast(
        sa.Column[object],
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "sync_runs",
        uuid_id(),
        sa.Column("source_system", sa.String(30), nullable=False),
        sa.Column("job_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pages_requested", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("items_received", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("items_inserted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("items_updated", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("items_unchanged", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("items_archived", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "items_pending_mapping", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("items_failed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name=op.f("ck_sync_runs_sync_completion_order"),
        ),
        sa.CheckConstraint(
            "pages_requested >= 0 AND items_received >= 0 AND items_inserted >= 0 "
            "AND items_updated >= 0 AND items_unchanged >= 0 AND items_archived >= 0 "
            "AND items_pending_mapping >= 0 AND items_failed >= 0",
            name=op.f("ck_sync_runs_sync_counters_nonnegative"),
        ),
        sa.CheckConstraint(
            "status IN ('started','succeeded','partial','failed','skipped')",
            name=op.f("ck_sync_runs_sync_status"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sync_runs"),
    )
    op.create_index("ix_sync_runs_correlation_id", "sync_runs", ["correlation_id"])
    op.create_index("ix_sync_runs_source_started", "sync_runs", ["source_system", "started_at"])
    op.create_table(
        "sync_item_errors",
        uuid_id(),
        sa.Column("sync_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_entity_type", sa.String(30), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("error_code", sa.String(50), nullable=False),
        sa.Column("field_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sync_run_id"],
            ["sync_runs.id"],
            name="fk_sync_item_errors_sync_run_id_sync_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sync_item_errors"),
    )
    op.create_index("ix_sync_item_errors_created_at", "sync_item_errors", ["created_at"])
    op.create_index("ix_sync_item_errors_external_id", "sync_item_errors", ["external_id"])
    op.create_index("ix_sync_item_errors_sync_run_id", "sync_item_errors", ["sync_run_id"])
    op.create_table(
        "audit_logs",
        uuid_id(),
        sa.Column("actor_type", sa.String(30), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column(
            "safe_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_correlation_id", "audit_logs", ["correlation_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_table(
        "system_alerts",
        uuid_id(),
        sa.Column("service", sa.String(100), nullable=False),
        sa.Column("alert_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'open'"), nullable=False),
        sa.Column("incident_key", sa.String(200), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("occurrence_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "safe_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "occurrence_count > 0", name=op.f("ck_system_alerts_alert_occurrence_positive")
        ),
        sa.CheckConstraint(
            "severity IN ('info','warning','error','critical')",
            name=op.f("ck_system_alerts_alert_severity"),
        ),
        sa.CheckConstraint(
            "status IN ('open','acknowledged','resolved')",
            name=op.f("ck_system_alerts_alert_status"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_system_alerts"),
    )
    op.create_index(
        "ix_system_alerts_status_last_seen", "system_alerts", ["status", "last_seen_at"]
    )
    op.create_index(
        "uq_system_alerts_open_incident",
        "system_alerts",
        ["service", "incident_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('open','acknowledged')"),
    )


def downgrade() -> None:
    op.drop_index("uq_system_alerts_open_incident", table_name="system_alerts")
    op.drop_index("ix_system_alerts_status_last_seen", table_name="system_alerts")
    op.drop_table("system_alerts")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_correlation_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_sync_item_errors_sync_run_id", table_name="sync_item_errors")
    op.drop_index("ix_sync_item_errors_external_id", table_name="sync_item_errors")
    op.drop_index("ix_sync_item_errors_created_at", table_name="sync_item_errors")
    op.drop_table("sync_item_errors")
    op.drop_index("ix_sync_runs_source_started", table_name="sync_runs")
    op.drop_index("ix_sync_runs_correlation_id", table_name="sync_runs")
    op.drop_table("sync_runs")
