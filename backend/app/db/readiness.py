"""Non-mutating Alembic revision readiness inspection."""

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text

SYNCHRONIZATION_TABLES = frozenset(
    {
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
    }
)


@dataclass(frozen=True)
class MigrationReadiness:
    status: str
    current_revision: str | None
    code_head: str


@dataclass(frozen=True)
class SynchronizationReadiness:
    status: str
    current_revision: str | None
    code_head: str
    missing_tables: tuple[str, ...]


def migration_head_status(engine: Engine, *, backend_dir: Path | None = None) -> MigrationReadiness:
    """Read revisions only; never creates, upgrades, or mutates schema."""
    root = backend_dir or Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    head = scripts.get_current_head()
    if head is None:
        raise RuntimeError("Alembic code has no single head")
    with engine.connect() as connection:
        if not inspect(connection).has_table("alembic_version"):
            return MigrationReadiness("uninitialized", None, head)
        current = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
    return MigrationReadiness("current" if current == head else "outdated", current, head)


def synchronization_readiness(
    engine: Engine, *, backend_dir: Path | None = None
) -> SynchronizationReadiness:
    """Check the migration head and frozen sync table inventory without mutation."""
    root = backend_dir or Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    head = scripts.get_current_head()
    if head is None:
        raise RuntimeError("Alembic code has no single head")
    with engine.connect() as connection:
        inspector = inspect(connection)
        tables = frozenset(inspector.get_table_names(schema="public"))
        missing = tuple(sorted(SYNCHRONIZATION_TABLES - tables))
        current = None
        if "alembic_version" in tables:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
    if current != head:
        status = "uninitialized" if current is None else "outdated"
    elif missing:
        status = "incomplete"
    else:
        status = "current"
    return SynchronizationReadiness(status, current, head, missing)
