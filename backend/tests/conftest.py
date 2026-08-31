"""Shared Gate 2 test configuration."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import Engine

from app.core.config import get_settings
from app.db.session import create_database_engine, validate_test_url

BACKEND_DIR = Path(__file__).resolve().parents[1]


def private_urls() -> tuple[str, str]:
    """Load private URLs without logging them and apply the fail-closed guard."""
    values = dotenv_values(BACKEND_DIR / ".env")
    development = values.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    test = values.get("TEST_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not isinstance(development, str):
        raise RuntimeError("DATABASE_URL is required")
    if not isinstance(test, str):
        raise RuntimeError("TEST_DATABASE_URL is required; database tests fail closed")
    validate_test_url(test, development_url=development)
    return development, test


@pytest.fixture(scope="session")
def test_database_engine() -> Generator[Engine]:
    """Return only the guarded, dedicated test engine."""
    _, test_url = private_urls()
    engine = create_database_engine(test_url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None]:
    """Prevent settings cache leakage between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
