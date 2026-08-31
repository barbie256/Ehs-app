"""Database foundation; Alembic is the only schema mutation mechanism."""

from app.db.base import Base

__all__ = ["Base"]
