"""Directorist v1 source-schema and fixture baseline tests."""

import json
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.integrations.directorist.schemas import DirectoristListingV1

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "directorist_listing_v1.json"
EXPECTED_SHA256 = "25b51d5f131c6986d6c08b2ed714f0ed8652ee54a617c7bea4f685334173dfe0"


def fixture_record() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["records"][0]


def test_fixture_sha256_is_frozen() -> None:
    assert sha256(FIXTURE.read_bytes()).hexdigest() == EXPECTED_SHA256


def test_fixture_declares_synthetic_and_private_data_free() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["synthetic"] is True
    assert payload["contains_real_credentials"] is False
    assert payload["contains_real_personal_contact_data"] is False
    record = payload["records"][0]
    assert all(record[field] == "" for field in ("email", "phone", "phone_2", "fax"))
    assert "password" not in FIXTURE.read_text(encoding="utf-8").lower()


def test_source_schema_parses_dates_decimal_and_empty_expiry() -> None:
    item = DirectoristListingV1.model_validate(fixture_record())
    assert item.price == Decimal("50000")
    assert item.date_modified_gmt is not None
    assert item.date_expired is None


def test_zero_price_is_preserved() -> None:
    record = fixture_record()
    record["price"] = 0
    assert DirectoristListingV1.model_validate(record).price == Decimal(0)


@pytest.mark.parametrize("field", ["id", "name", "slug", "permalink", "status"])
def test_required_identity_fields_are_rejected_when_missing(field: str) -> None:
    record = fixture_record()
    record.pop(field)
    with pytest.raises(ValidationError):
        DirectoristListingV1.model_validate(record)


def test_unknown_names_are_observable_without_values() -> None:
    record = fixture_record()
    record["future_secret_value"] = "never-observe-this"
    item = DirectoristListingV1.model_validate(record)
    assert item.unknown_field_names == ("future_secret_value",)
    assert "never-observe-this" not in repr(item.unknown_field_names)


def test_invalid_date_and_unsafe_url_are_rejected() -> None:
    record = fixture_record()
    record["date_modified_gmt"] = "not-a-date"
    with pytest.raises(ValidationError):
        DirectoristListingV1.model_validate(record)
    record = fixture_record()
    record["permalink"] = "javascript:alert(1)"
    with pytest.raises(ValidationError):
        DirectoristListingV1.model_validate(record)
