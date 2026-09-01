"""Safe taxonomy collection parsing tests."""

import pytest

from app.integrations.directorist.errors import DirectoristError
from app.services.catalogue_sync import CatalogueSyncService


def test_taxonomy_snapshots_are_sanitized_and_sorted() -> None:
    records = [{"id": 2, "name": "<b>Second</b>"}, {"id": 1, "name": "First"}]
    assert CatalogueSyncService._safe_taxonomy_records(records) == [
        ("1", "First"),
        ("2", "Second"),
    ]


def test_invalid_taxonomy_identity_fails_without_raw_value() -> None:
    with pytest.raises(DirectoristError, match="invalid identity"):
        CatalogueSyncService._safe_taxonomy_records([{"id": "secret", "name": "ignored"}])
