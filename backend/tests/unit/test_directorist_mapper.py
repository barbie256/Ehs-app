"""Pure normalized mapper, sanitization, taxonomy, and public projection tests."""

import json
from pathlib import Path

import pytest

from app.integrations.directorist.errors import DirectoristMappingError, DirectoristSchemaError
from app.integrations.directorist.mapper import map_listing, to_detail, to_summary
from app.integrations.directorist.schemas import DirectoristListingV1
from app.schemas.catalogue import CanonicalMapping

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "directorist_listing_v1.json"


class FakeResolver:
    def __init__(self, mappings: dict[int, CanonicalMapping]) -> None:
        self.mappings = mappings

    def resolve_category(self, external_id: int) -> CanonicalMapping | None:
        return self.mappings.get(external_id)


def source(**changes: object) -> DirectoristListingV1:
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))["records"][0]
    record.update(changes)
    return DirectoristListingV1.model_validate(record)


def mapping(marketplace: str = "construction", category: str = "cement") -> CanonicalMapping:
    return CanonicalMapping(
        marketplace_code=marketplace,
        marketplace_name=marketplace.title(),
        category_code=category,
        category_name=category.title(),
    )


def test_mapped_listing_sanitizes_and_keeps_currency_unknown() -> None:
    item = source(
        description=(
            '<p onclick="bad()">Safe<script>secret()</script><a href="javascript:bad">link</a></p>'
        ),
        short_description="<b>Brief</b>",
    )
    normalized = map_listing(item, FakeResolver({29: mapping()}))
    assert "script" not in normalized.description and "onclick" not in normalized.description
    assert "javascript" not in normalized.description
    assert normalized.summary == "Brief"
    assert normalized.currency is None
    assert normalized.classification_status == "mapped"


def test_hidden_contacts_are_removed_and_visible_contacts_are_normalized() -> None:
    hidden = map_listing(
        source(email="synthetic@example.invalid", phone="+256000000", owner_contact_hidden=True),
        FakeResolver({29: mapping()}),
    )
    assert hidden.contacts == []
    visible = map_listing(
        source(email="synthetic@example.invalid", phone=" +256000000 ", owner_contact_hidden=False),
        FakeResolver({29: mapping()}),
    )
    assert {item.contact_type for item in visible.contacts} == {"email", "phone"}


def test_checksum_is_deterministic_and_yoast_and_links_are_omitted() -> None:
    first = source(yoast_head="ignored-one")
    second = source(yoast_head="ignored-two", _links={"unsafe": "ignored"})
    resolver = FakeResolver({29: mapping()})
    assert (
        map_listing(first, resolver).source_checksum
        == map_listing(second, resolver).source_checksum
    )


def test_unknown_and_empty_categories_are_pending() -> None:
    assert map_listing(source(), FakeResolver({})).classification_status == "pending"
    assert map_listing(source(categories=[]), FakeResolver({})).classification_status == "pending"


@pytest.mark.parametrize(
    ("name", "marketplace", "category"),
    [
        ("Cement", "construction", "cement"),
        ("Commercial Properties", "property", "commercial_properties"),
        ("Furniture", "home_interior", "furniture"),
        ("Engineers", "professional_services", "engineers"),
    ],
)
def test_canonical_mapping_examples(name: str, marketplace: str, category: str) -> None:
    item = source(categories=[{"id": 77, "name": name, "slug": category}])
    result = map_listing(item, FakeResolver({77: mapping(marketplace, category)}))
    assert result.canonical_mappings[0].marketplace_code == marketplace


def test_ambiguous_marketplaces_fail_safely() -> None:
    item = source(categories=[{"id": 1, "name": "One"}, {"id": 2, "name": "Two"}])
    with pytest.raises(DirectoristMappingError):
        map_listing(item, FakeResolver({1: mapping("property"), 2: mapping("construction")}))


def test_coordinate_ranges_are_enforced_and_zero_price_preserved() -> None:
    with pytest.raises(DirectoristSchemaError):
        map_listing(source(latitude="91"), FakeResolver({}))
    assert map_listing(source(price=0), FakeResolver({})).price == 0


def test_public_summary_and_detail_allowlists() -> None:
    normalized = map_listing(
        source(owner_contact_hidden=False, email="synthetic@example.invalid"),
        FakeResolver({29: mapping()}),
    )
    summary = to_summary(normalized)
    detail = to_detail(normalized)
    assert summary.rating is None and summary.contact_available is True
    assert (
        "contacts" not in summary.model_fields_set
        and "source_author_id" not in summary.model_dump()
    )
    assert detail.contacts and "source_author_id" not in detail.model_dump()


def test_missing_image_is_safe() -> None:
    assert to_summary(map_listing(source(images=[]), FakeResolver({}))).primary_image is None
