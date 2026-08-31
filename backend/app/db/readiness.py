"""Non-mutating Alembic revision readiness inspection."""

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text


@dataclass(frozen=True)
class MigrationReadiness:
    status: str
    current_revision: str | None
    code_head: str


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
