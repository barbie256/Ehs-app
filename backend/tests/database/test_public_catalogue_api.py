"""Guarded synthetic PostgreSQL tests for the public catalogue API."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import Engine, delete, event, func, select
from sqlalchemy.orm import Session

from app.api.catalogue import catalogue_session
from app.db.models.catalogue import (
    Listing,
    ListingCategory,
    ListingContact,
    ListingLocation,
    ListingMedia,
    ListingSourcePayload,
)
from app.db.models.taxonomy import Category, Location, Marketplace
from app.main import create_app


@contextmanager
def rollback_session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def seed_public_rows(session: Session) -> dict[str, UUID]:
    marketplace = Marketplace(code="api-construction", name="API Construction", sort_order=1)
    category = Category(
        marketplace_id=marketplace.id,
        code="api-cement",
        slug="api-cement",
        name="API Cement",
        sort_order=1,
    )
    africa = Location(
        country_code="AF", location_type="continent", name="API Africa", slug="api-africa"
    )
    session.add_all([marketplace, africa])
    session.flush()
    category.marketplace_id = marketplace.id
    uganda = Location(
        parent_id=africa.id,
        country_code="UG",
        location_type="country",
        name="API Uganda",
        slug="api-uganda",
    )
    session.add_all([category, uganda])
    session.flush()
    kampala = Location(
        parent_id=uganda.id,
        country_code="UG",
        location_type="city",
        name="API Kampala",
        slug="api-kampala",
    )
    session.add(kampala)
    session.flush()

    def listing(
        external_id: str,
        *,
        status: str = "active",
        classification: str = "mapped",
        mapped: bool = True,
    ) -> Listing:
        record = Listing(
            source_system="api-test",
            external_id=external_id,
            marketplace_id=marketplace.id if mapped else None,
            title=f"Synthetic public {external_id}",
            summary="Synthetic searchable summary",
            description="Synthetic description",
            source_status="publish",
            status=status,
            classification_status=classification,
            price_amount=10,
            currency=None,
            pricing_type="fixed",
            featured=external_id == "visible",
            contacts_hidden=False,
            source_url="https://example.invalid/public",
            source_modified_at=datetime(2026, 1, 1, tzinfo=UTC),
            source_checksum="a" * 64,
        )
        session.add(record)
        session.flush()
        session.add(
            ListingSourcePayload(
                listing_id=record.id,
                schema_version="synthetic-v1",
                sanitized_payload={
                    "slug": "source-slug",
                    "tagline": "Synthetic",
                    "average_rating": "4.5",
                    "rating_count": 2,
                },
                payload_checksum="b" * 64,
            )
        )
        if mapped:
            session.add(
                ListingCategory(
                    listing_id=record.id,
                    category_id=category.id,
                    is_primary=True,
                    mapping_source="synthetic",
                )
            )
        return record

    visible = listing("visible")
    second = listing("second")
    pending = listing("pending", classification="pending", mapped=False)
    archived = listing("archived", status="archived")
    no_category = listing("no-category")
    session.flush()
    session.add_all(
        [
            ListingLocation(listing_id=visible.id, location_id=kampala.id, is_primary=True),
            ListingLocation(listing_id=second.id, location_id=kampala.id, is_primary=True),
            ListingContact(
                listing_id=visible.id,
                contact_type="email",
                normalized_value="private@example.invalid",
                display_value="private@example.invalid",
                is_public=True,
                source_field="email",
            ),
            ListingMedia(
                listing_id=visible.id,
                source_system="synthetic",
                source_external_id="image",
                source_url="https://example.invalid/image.jpg",
                media_type="image",
                alt_text="Synthetic",
                position=0,
            ),
        ]
    )
    session.execute(delete(ListingCategory).where(ListingCategory.listing_id == no_category.id))
    session.flush()
    assert pending.id and archived.id
    return {
        "visible": visible.id,
        "pending": pending.id,
        "archived": archived.id,
        "no_category": no_category.id,
    }


async def request(app: object, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path)


def test_public_endpoints_visibility_filters_privacy_and_bounded_queries(
    test_database_engine: Engine,
) -> None:
    with rollback_session(test_database_engine) as session:
        identifiers = seed_public_rows(session)
        application = create_app()

        def override() -> Iterator[Session]:
            yield session

        application.dependency_overrides[catalogue_session] = override
        queries = 0

        def count_query(*_args: object) -> None:
            nonlocal queries
            queries += 1

        event.listen(session.bind, "before_cursor_execute", count_query)
        try:
            response = asyncio.run(
                request(application, "/api/v1/listings?q=synthetic&featured=true")
            )
            list_queries = queries
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 1
            assert len(body["items"]) == 1
            assert list_queries <= 4
            serialized = response.text.casefold()
            for forbidden in (
                "private@example.invalid",
                "external_id",
                "payload",
                "author",
                "plan",
            ):
                assert forbidden not in serialized

            for location in ("api-kampala", "api-uganda", "api-africa"):
                assert (
                    asyncio.run(
                        request(application, f"/api/v1/listings?location={location}")
                    ).json()["total"]
                    == 2
                )
            assert (
                asyncio.run(request(application, "/api/v1/listings?location=unknown")).json()[
                    "total"
                ]
                == 0
            )
            assert (
                asyncio.run(request(application, "/api/v1/listings?marketplace=unknown")).json()[
                    "total"
                ]
                == 0
            )
            assert (
                asyncio.run(
                    request(application, "/api/v1/listings?marketplace=api-construction")
                ).json()["total"]
                == 2
            )
            assert (
                asyncio.run(request(application, "/api/v1/listings?category=unknown")).json()[
                    "total"
                ]
                == 0
            )
            assert (
                asyncio.run(request(application, "/api/v1/listings?category=api-cement")).json()[
                    "total"
                ]
                == 2
            )
            assert asyncio.run(request(application, "/api/v1/listings?q=x")).status_code == 422
            ordered = asyncio.run(
                request(
                    application,
                    "/api/v1/listings?marketplace=api-construction&per_page=1&order_by=title&order=asc",
                )
            ).json()
            assert (ordered["page"], ordered["per_page"], ordered["total_pages"]) == (1, 1, 2)
            assert ordered["has_next"] is True

            detail = asyncio.run(request(application, f"/api/v1/listings/{identifiers['visible']}"))
            assert detail.status_code == 200
            assert detail.json()["contact_available"] is True
            assert "private@example.invalid" not in detail.text
            missing = UUID("00000000-0000-0000-0000-000000000099")
            assert (
                asyncio.run(request(application, f"/api/v1/listings/{missing}")).status_code == 404
            )
            for hidden in ("pending", "archived", "no_category"):
                hidden_response = asyncio.run(
                    request(application, f"/api/v1/listings/{identifiers[hidden]}")
                )
                assert hidden_response.status_code == 404
                assert hidden_response.json() == {"detail": "Listing not found"}

            marketplaces = asyncio.run(request(application, "/api/v1/marketplaces")).json()
            assert (
                next(item for item in marketplaces if item["code"] == "api-construction")[
                    "listing_count"
                ]
                == 2
            )
            categories = asyncio.run(
                request(application, "/api/v1/categories?marketplace=api-construction")
            ).json()
            assert categories == [
                {
                    "code": "api-cement",
                    "name": "API Cement",
                    "marketplace": "api-construction",
                    "parent": None,
                    "listing_count": 2,
                }
            ]
            tree = asyncio.run(request(application, "/api/v1/locations")).json()
            api_tree = next(item for item in tree if item["code"] == "api-africa")
            assert api_tree["listing_count"] == 2
        finally:
            event.remove(session.bind, "before_cursor_execute", count_query)

        assert (
            session.scalar(
                select(func.count()).select_from(Listing).where(Listing.source_system == "api-test")
            )
            == 5
        )
