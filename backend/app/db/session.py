"""Explicit database URL validation and session lifecycle helpers."""

from collections.abc import Generator
from contextlib import contextmanager
from urllib.parse import unquote

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
KNOWN_PRODUCTION_HOST_PARTS = {"neon.tech", "ehsmall.com"}


class DatabaseSafetyError(ValueError):
    """A redacted failure at a local database safety boundary."""


def _validate_local_url(raw_url: str, *, expected_database: str) -> URL:
    """Parse and validate a dedicated local EHS URL without returning secrets in errors."""
    try:
        url = make_url(raw_url)
        host = (url.host or "").lower()
        database = unquote(url.database or "")
        user = unquote(url.username or "")
    except Exception:
        raise DatabaseSafetyError("database URL is invalid") from None
    if host not in LOCAL_HOSTS or any(part in host for part in KNOWN_PRODUCTION_HOST_PARTS):
        raise DatabaseSafetyError("database host is not an approved local host")
    if database != expected_database:
        raise DatabaseSafetyError(f"database name must be {expected_database}")
    if user != "ehs_mall_local":
        raise DatabaseSafetyError("database role must be ehs_mall_local")
    return url


def validate_development_url(raw_url: str) -> URL:
    return _validate_local_url(raw_url, expected_database="ehs_mall_dev")


def validate_test_url(raw_url: str | None, *, development_url: str | None = None) -> URL:
    if not raw_url:
        raise DatabaseSafetyError("TEST_DATABASE_URL is required for database tests")
    test_url = _validate_local_url(raw_url, expected_database="ehs_mall_test")
    if development_url:
        try:
            if test_url.normalized_query == make_url(development_url).normalized_query and str(
                test_url.set(password="REDACTED")
            ) == str(make_url(development_url).set(password="REDACTED")):
                raise DatabaseSafetyError("test and development database URLs must differ")
        except DatabaseSafetyError:
            raise
        except Exception:
            raise DatabaseSafetyError("development database URL is invalid") from None
    return test_url


def redact_database_url(raw_url: str) -> str:
    """Return a safe URL representation or a fixed invalid marker."""
    try:
        return make_url(raw_url).render_as_string(hide_password=True)
    except Exception:
        return "<invalid database URL>"


def create_database_engine(raw_url: str) -> Engine:
    """Create a lazy engine; no connection occurs at import or construction."""
    return create_engine(raw_url, pool_pre_ping=True)


@contextmanager
def session_scope(engine: Engine) -> Generator[Session]:
    """Commit a unit of work or roll it back, always closing the session."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
