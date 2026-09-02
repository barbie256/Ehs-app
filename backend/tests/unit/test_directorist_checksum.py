"""Versioned canonical Directorist source-checksum contract tests."""

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from app.integrations.directorist import checksum
from app.integrations.directorist.mapper import map_listing
from app.integrations.directorist.schemas import DirectoristListingV1
from app.schemas.catalogue import CanonicalMapping, NormalizedListing

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "directorist_listing_v1.json"


class Resolver:
    def __init__(self, mappings: dict[int, CanonicalMapping] | None = None) -> None:
        self.mappings = mappings or {}

    def resolve_category(self, external_id: int) -> CanonicalMapping | None:
        return self.mappings.get(external_id)


def record(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = deepcopy(json.loads(FIXTURE.read_text())["records"][0])
    payload.update(changes)
    return payload


def normalized(payload: dict[str, object], resolver: Resolver | None = None) -> NormalizedListing:
    return map_listing(DirectoristListingV1.model_validate(payload), resolver or Resolver())


def test_checksum_contract_version_is_explicit_and_hashed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = normalized(record())
    original = checksum.calculate_source_checksum(item)
    assert checksum.SOURCE_CHECKSUM_VERSION == 2
    monkeypatch.setattr(checksum, "SOURCE_CHECKSUM_VERSION", 3)
    assert checksum.calculate_source_checksum(item) != original


def test_normalized_field_inventory_requires_an_explicit_decision() -> None:
    assert set(NormalizedListing.model_fields) == (
        checksum.SOURCE_CHECKSUM_INCLUDED_FIELDS | checksum.SOURCE_CHECKSUM_EXCLUDED_FIELDS
    )
    assert not (checksum.SOURCE_CHECKSUM_INCLUDED_FIELDS & checksum.SOURCE_CHECKSUM_EXCLUDED_FIELDS)


def test_identical_and_dictionary_reordered_records_match() -> None:
    payload = record()
    reordered = dict(reversed(list(payload.items())))
    assert normalized(payload).source_checksum == normalized(reordered).source_checksum


@pytest.mark.parametrize("field", ["categories", "locations", "images"])
def test_collection_permutations_match(field: str) -> None:
    payload = record()
    additions: dict[str, dict[str, object]] = {
        "categories": {"id": 30, "name": "Second", "slug": "second"},
        "locations": {"id": 52, "name": "Second", "slug": "second"},
        "images": {
            "id": 990002,
            "src": "https://example.invalid/media/second.jpg",
            "alt": "Second",
            "position": 1,
        },
    }
    values = list(cast(list[dict[str, object]], payload[field]))
    values.append(additions[field])
    payload[field] = values
    permuted = deepcopy(payload)
    permuted[field] = list(reversed(values))
    assert normalized(payload).source_checksum == normalized(permuted).source_checksum


def test_contact_permutations_match() -> None:
    item = normalized(
        record(
            owner_contact_hidden=False,
            email="synthetic@example.invalid",
            phone="+256000000",
        )
    )
    permuted = item.model_copy(update={"contacts": list(reversed(item.contacts))})
    assert checksum.calculate_source_checksum(item) == checksum.calculate_source_checksum(permuted)


@pytest.mark.parametrize(
    ("left", "right"),
    [(0, "0.00"), ("-0.000", 0), (1, "1.00"), ("1000", "1E+3")],
)
def test_equivalent_decimal_encodings_match(left: object, right: object) -> None:
    assert (
        normalized(record(price=left)).source_checksum
        == normalized(record(price=right)).source_checksum
    )


def test_equivalent_aware_datetime_instants_match() -> None:
    first = normalized(record(date_modified_gmt="2026-08-20T08:30:00Z"))
    second = normalized(record(date_modified_gmt="2026-08-20T11:30:00+03:00"))
    assert first.source_checksum == second.source_checksum


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("date_modified_gmt", "2026-08-21T08:30:00Z"),
        ("latitude", "1.5"),
        ("map_hidden", True),
        ("featured", True),
        ("price_range", "different"),
        ("description", "<p>Different</p>"),
        ("phone", "+256000000"),
    ],
)
def test_persisted_source_owned_changes_change_checksum(field: str, value: object) -> None:
    base = record(owner_contact_hidden=False)
    assert normalized(base).source_checksum != normalized({**base, field: value}).source_checksum


def test_media_change_changes_checksum() -> None:
    changed = record()
    images = deepcopy(cast(list[dict[str, object]], changed["images"]))
    images[0]["alt"] = "Changed"
    changed["images"] = images
    assert normalized(record()).source_checksum != normalized(changed).source_checksum


def test_resolver_and_unknown_raw_fields_do_not_change_checksum() -> None:
    mapping = CanonicalMapping(
        marketplace_code="construction",
        marketplace_name="Construction",
        category_code="cement",
        category_name="Cement",
    )
    base = record()
    unknown = {**base, "future_private_field": "excluded"}
    assert normalized(base).source_checksum == normalized(unknown).source_checksum
    assert (
        normalized(base).source_checksum
        == normalized(base, Resolver({29: mapping})).source_checksum
    )


def test_checksum_calculation_logs_no_source_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "must-not-be-logged"
    checksum.calculate_source_checksum(normalized(record(description=sentinel)))
    assert sentinel not in caplog.text
