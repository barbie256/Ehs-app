"""Offline public catalogue policy and privacy tests."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.api import catalogue as catalogue_api
from app.db.readiness import SynchronizationReadiness
from app.repositories.public_catalogue import ListingFilters, ListingProjection
from app.schemas.public_catalogue import ListingOrderBy, ListingSummaryResponse, SortOrder
from app.services.public_catalogue import PublicCatalogueService, normalize_search, public_slug


def projection(**changes: object) -> ListingProjection:
    values: dict[str, object] = {
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "title": "Synthetic Safety Listing",
        "summary": "Synthetic summary",
        "marketplace_code": "construction",
        "marketplace_name": "Construction",
        "category_code": "cement",
        "category_name": "Cement",
        "location_code": "kampala",
        "location_name": "Kampala",
        "price": Decimal("0"),
        "currency": None,
        "pricing_type": "fixed",
        "featured": False,
        "rating": Decimal("4.5"),
        "rating_count": 2,
        "primary_image_url": "https://example.invalid/image.jpg",
        "primary_image_alt": "Synthetic image",
        "contact_available": True,
        "source_url": "https://example.invalid/listing",
        "description": "Synthetic description",
        "tagline": "Synthetic tagline",
        "source_modified_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(changes)
    return ListingProjection(**values)  # type: ignore[arg-type]


class FakeRepository:
    def listings(self, filters: ListingFilters) -> tuple[int, list[ListingProjection]]:
        return 21, [projection()]


def test_search_normalization_and_wildcard_escaping() -> None:
    assert normalize_search(None) is None
    assert normalize_search("   ") is None
    assert normalize_search("  20%_off\\now  ") == r"20\%\_off\\now"
    with pytest.raises(ValueError):
        normalize_search("x")
    with pytest.raises(ValueError):
        normalize_search("x" * 101)


def test_pagination_and_controlled_sort_contracts() -> None:
    filters = ListingFilters(
        page=2,
        per_page=20,
        order_by=ListingOrderBy.RATING,
        order=SortOrder.ASC,
    )
    response = PublicCatalogueService(FakeRepository()).listings(filters)  # type: ignore[arg-type]
    assert (response.total_pages, response.has_next, response.has_previous) == (2, False, True)
    assert {item.value for item in ListingOrderBy} == {"newest", "title", "rating"}
    assert {item.value for item in SortOrder} == {"asc", "desc"}


def test_summary_allowlist_excludes_private_and_source_identifiers() -> None:
    summary = PublicCatalogueService._summary(projection())
    assert set(ListingSummaryResponse.model_fields) == {
        "id",
        "title",
        "slug",
        "summary",
        "marketplace",
        "primary_category",
        "location",
        "price",
        "currency",
        "pricing_type",
        "featured",
        "rating",
        "rating_count",
        "primary_image",
        "contact_available",
        "source_url",
    }
    serialized = summary.model_dump_json()
    for forbidden in (
        "email",
        "phone",
        "author",
        "plan",
        "external_id",
        "payload",
        "coordinate",
        "address",
    ):
        assert forbidden not in serialized.casefold()


def test_https_media_enforcement_and_stable_public_slug() -> None:
    hidden_image = PublicCatalogueService._summary(
        projection(primary_image_url="http://example.invalid/image.jpg")
    )
    assert hidden_image.primary_image is None
    assert (
        PublicCatalogueService._summary(projection(source_url="http://example.invalid")).source_url
        is None
    )
    identifier = UUID("00000000-0000-0000-0000-000000000001")
    assert public_slug("Safe Example", identifier) == "safe-example-00000000"


class FakeEngine:
    disposed = False

    def dispose(self) -> None:
        self.disposed = True


class FakeSession:
    closed = False
    rollbacks = 0

    def execute(self, _statement: object) -> None:
        return None

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def test_readiness_failure_is_safe_503_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    monkeypatch.setattr(catalogue_api, "create_database_engine", lambda _url: engine)
    monkeypatch.setattr(
        catalogue_api,
        "synchronization_readiness",
        lambda _engine: SynchronizationReadiness("incomplete", None, "head", ("private",)),
    )
    dependency = catalogue_api.catalogue_session()
    with pytest.raises(HTTPException) as error:
        next(dependency)
    assert (error.value.status_code, error.value.detail) == (
        503,
        "Catalogue temporarily unavailable",
    )
    assert engine.disposed is True


def test_success_session_is_rolled_back_closed_and_engine_disposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    session = FakeSession()
    monkeypatch.setattr(catalogue_api, "create_database_engine", lambda _url: engine)
    monkeypatch.setattr(
        catalogue_api,
        "synchronization_readiness",
        lambda _engine: SynchronizationReadiness("current", "head", "head", ()),
    )

    class Factory:
        def __call__(self) -> FakeSession:
            return session

    monkeypatch.setattr(catalogue_api, "sessionmaker", lambda **_values: Factory())
    dependency = catalogue_api.catalogue_session()
    yielded: object = next(dependency)
    assert yielded is session
    with pytest.raises(StopIteration):
        next(dependency)
    assert session.closed is True
    assert session.rollbacks >= 1
    assert engine.disposed is True
