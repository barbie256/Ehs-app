"""Shared Gate 2 test configuration."""

from collections.abc import Generator

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None, None, None]:
    """Prevent settings cache leakage between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
