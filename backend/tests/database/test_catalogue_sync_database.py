"""Guarded PostgreSQL integration tests for Gate 5A synchronization."""

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.db.models.catalogue import (
    Listing,
    ListingCategory,
    ListingContact,
    ListingLocation,
    ListingMedia,
    ListingSourcePayload,
    SourceTaxonomyMapping,
)
from app.db.models.operations import SyncItemError, SyncRun
from app.db.models.taxonomy import Category, Location, Marketplace
from app.integrations.directorist.schemas import (
    DirectoristListingV1,
    DirectoristValidatedPage,
    ListingValidationFailure,
)
from app.repositories.sync import SyncRepository
from app.services.catalogue_sync import CatalogueSyncService
from app.services.taxonomy_seed import seed_canonical_taxonomy

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "directorist_listing_v1.json"


class FakeSource:
    def __init__(self, items: list[DirectoristListingV1], *, malformed: bool = False) -> None:
        self.items = items
        self.malformed = malformed

    async def get_directories(self) -> list[dict[str, Any]]:
        return [{"id": 3, "name": "Synthetic Directory"}]

    async def get_all_categories(self, per_page: int) -> list[dict[str, Any]]:
        return [{"id": 29, "name": "Cement snapshot"}]

    async def get_locations(self) -> list[dict[str, Any]]:
        return [{"id": 51, "name": "Synthetic Kampala"}]

    async def get_validated_listings_page(
        self, page: int, per_page: int
    ) -> DirectoristValidatedPage:
        return DirectoristValidatedPage(
            items=self.items,
            failures=[ListingValidationFailure(external_id="900099")] if self.malformed else [],
            current_page=page,
            page_size=per_page,
            total_items=len(self.items) + int(self.malformed),
            total_pages=1,
            next_page=None,
        )


def _fixture_listing(**changes: object) -> DirectoristListingV1:
    payload = json.loads(FIXTURE_PATH.read_text())["records"][0]
    payload.update(changes)
    return DirectoristListingV1.model_validate(payload)


def _prepare(session: Session) -> None:
    session.execute(delete(SyncRun).where(SyncRun.correlation_id.like("gate5a-%")))
    session.execute(
        delete(Listing).where(
            Listing.source_system == "directorist", Listing.external_id.like("900%")
        )
    )
    session.execute(
        delete(SourceTaxonomyMapping).where(
            SourceTaxonomyMapping.source_system == "directorist",
            SourceTaxonomyMapping.source_external_id.in_(["3", "29", "51"]),
        )
    )
    seed_canonical_taxonomy(session)
    marketplace = session.scalar(select(Marketplace).where(Marketplace.code == "construction"))
    assert marketplace is not None
    category = session.scalar(
        select(Category).where(Category.marketplace_id == marketplace.id, Category.code == "cement")
    )
    assert category is not None
    location = session.scalar(select(Location).where(Location.slug == "gate5a-kampala"))
    if location is None:
        location = Location(
            country_code="UG",
            location_type="city",
            name="Gate 5A Kampala",
            slug="gate5a-kampala",
        )
        session.add(location)
        session.flush()
    session.add_all(
        [
            SourceTaxonomyMapping(
                source_system="directorist",
                source_taxonomy="category",
                source_external_id="29",
                source_name_snapshot="Old approved name",
                marketplace_id=marketplace.id,
                category_id=category.id,
                mapping_status="approved",
            ),
            SourceTaxonomyMapping(
                source_system="directorist",
                source_taxonomy="location",
                source_external_id="51",
                source_name_snapshot="Old location name",
                location_id=location.id,
                mapping_status="approved",
            ),
        ]
    )
    session.commit()


def test_sync_idempotency_partial_safety_and_complete_archival(
    test_database_engine: Engine,
) -> None:
    with (
        test_database_engine.connect() as connection,
        Session(bind=connection, expire_on_commit=False) as session,
    ):
        _prepare(session)
        first = asyncio.run(
            CatalogueSyncService(session, FakeSource([_fixture_listing()])).run("gate5a-first")
        )
        assert (first.status, first.counts.items_inserted) == ("succeeded", 1)
        second = asyncio.run(
            CatalogueSyncService(session, FakeSource([_fixture_listing()])).run("gate5a-second")
        )
        assert (second.status, second.counts.items_unchanged) == ("succeeded", 1)

        partial = asyncio.run(
            CatalogueSyncService(session, FakeSource([], malformed=True)).run("gate5a-partial")
        )
        listing = session.scalar(select(Listing).where(Listing.external_id == "900001"))
        assert listing is not None
        assert partial.status == "partial"
        assert listing.status == "active"
        error = session.scalar(
            select(SyncItemError).join(SyncRun).where(SyncRun.correlation_id == "gate5a-partial")
        )
        assert error is not None
        assert error.field_summary == "listing"

        complete = asyncio.run(CatalogueSyncService(session, FakeSource([])).run("gate5a-complete"))
        session.refresh(listing)
        assert complete.status == "succeeded"
        assert complete.counts.items_archived == 1
        assert listing.status == "unavailable"

        approved = session.scalar(
            select(SourceTaxonomyMapping).where(
                SourceTaxonomyMapping.source_taxonomy == "category",
                SourceTaxonomyMapping.source_external_id == "29",
            )
        )
        directory = session.scalar(
            select(SourceTaxonomyMapping).where(
                SourceTaxonomyMapping.source_taxonomy == "directory",
                SourceTaxonomyMapping.source_external_id == "3",
            )
        )
        assert approved is not None
        assert directory is not None
        assert approved.mapping_status == "approved"
        assert approved.source_name_snapshot == "Cement snapshot"
        assert directory.mapping_status == "pending"


def test_advisory_lock_prevents_overlap(test_database_engine: Engine) -> None:
    with (
        test_database_engine.connect() as first_connection,
        test_database_engine.connect() as second_connection,
        Session(bind=first_connection) as first,
        Session(bind=second_connection) as second,
    ):
        first_repository = SyncRepository(first)
        second_repository = SyncRepository(second)
        assert first_repository.try_lock() is True
        first.commit()
        assert second_repository.try_lock() is False
        second.commit()
        assert first_repository.unlock() is True
        first.commit()


def test_canonical_checksum_and_classification_only_reconciliation(
    test_database_engine: Engine,
) -> None:
    with (
        test_database_engine.connect() as connection,
        Session(bind=connection, expire_on_commit=False) as session,
    ):
        _prepare(session)
        item = _fixture_listing(
            owner_contact_hidden=False,
            email="synthetic@example.invalid",
            phone="+256000000",
        )
        first = asyncio.run(
            CatalogueSyncService(session, FakeSource([item])).run("gate5a-checksum-first")
        )
        assert (first.counts.items_inserted, first.counts.items_failed) == (1, 0)
        listing = session.scalar(select(Listing).where(Listing.external_id == "900001"))
        assert listing is not None
        payload = session.get(ListingSourcePayload, listing.id)
        assert payload is not None
        original_payload_observed_at = payload.observed_at
        original_media_ids = set(
            session.scalars(select(ListingMedia.id).where(ListingMedia.listing_id == listing.id))
        )
        original_contact_ids = set(
            session.scalars(
                select(ListingContact.id).where(ListingContact.listing_id == listing.id)
            )
        )

        identical = asyncio.run(
            CatalogueSyncService(session, FakeSource([item])).run("gate5a-checksum-identical")
        )
        assert identical.counts.items_unchanged == 1

        mapping = session.scalar(
            select(SourceTaxonomyMapping).where(
                SourceTaxonomyMapping.source_taxonomy == "category",
                SourceTaxonomyMapping.source_external_id == "29",
            )
        )
        assert mapping is not None
        alternate = session.scalar(
            select(Category).where(
                Category.marketplace_id == mapping.marketplace_id,
                Category.id != mapping.category_id,
            )
        )
        assert alternate is not None
        mapping.category_id = alternate.id
        session.commit()

        remapped = asyncio.run(
            CatalogueSyncService(session, FakeSource([item])).run("gate5a-checksum-remapped")
        )
        assert remapped.counts.items_updated == 1
        category_ids = set(
            session.scalars(
                select(ListingCategory.category_id).where(ListingCategory.listing_id == listing.id)
            )
        )
        assert category_ids == {alternate.id}
        session.refresh(payload)
        assert payload.observed_at == original_payload_observed_at
        assert original_media_ids == set(
            session.scalars(select(ListingMedia.id).where(ListingMedia.listing_id == listing.id))
        )
        assert original_contact_ids == set(
            session.scalars(
                select(ListingContact.id).where(ListingContact.listing_id == listing.id)
            )
        )

        stable = asyncio.run(
            CatalogueSyncService(session, FakeSource([item])).run("gate5a-checksum-stable")
        )
        assert stable.counts.items_unchanged == 1

        mapping.mapping_status = "rejected"
        session.commit()
        pending = asyncio.run(
            CatalogueSyncService(session, FakeSource([item])).run("gate5a-checksum-pending")
        )
        session.refresh(listing)
        assert pending.counts.items_updated == 1
        assert listing.classification_status == "pending"
        assert listing.marketplace_id is None
        assert not session.scalars(
            select(ListingCategory).where(ListingCategory.listing_id == listing.id)
        ).all()

        pending_stable = asyncio.run(
            CatalogueSyncService(session, FakeSource([item])).run("gate5a-checksum-pending-stable")
        )
        assert pending_stable.counts.items_unchanged == 1

        mapping.mapping_status = "approved"
        session.commit()
        approved = asyncio.run(
            CatalogueSyncService(session, FakeSource([item])).run("gate5a-checksum-approved")
        )
        session.refresh(listing)
        assert approved.counts.items_updated == 1
        assert listing.classification_status == "mapped"
        assert listing.marketplace_id is not None

        approved_stable = asyncio.run(
            CatalogueSyncService(session, FakeSource([item])).run("gate5a-checksum-approved-stable")
        )
        assert approved_stable.counts.items_unchanged == 1


def test_canonical_source_representations_are_database_idempotent(
    test_database_engine: Engine,
) -> None:
    with (
        test_database_engine.connect() as connection,
        Session(bind=connection, expire_on_commit=False) as session,
    ):
        _prepare(session)
        categories = [
            {"id": 29, "name": "Cement", "slug": "cement"},
            {"id": 30, "name": "Second", "slug": "second"},
        ]
        locations = [
            {"id": 51, "name": "Kampala", "slug": "kampala"},
            {"id": 52, "name": "Second", "slug": "second"},
        ]
        images = [
            {"id": 990001, "src": "https://example.invalid/media/first.jpg", "position": 0},
            {"id": 990002, "src": "https://example.invalid/media/second.jpg", "position": 1},
        ]
        first_item = _fixture_listing(
            categories=categories,
            locations=locations,
            images=images,
            price=50000,
            date_modified_gmt="2026-08-20T08:30:00Z",
            owner_contact_hidden=False,
            email="synthetic@example.invalid",
        )
        first = asyncio.run(
            CatalogueSyncService(session, FakeSource([first_item])).run("gate5a-canonical-first")
        )
        assert first.counts.items_inserted == 1

        equivalent = _fixture_listing(
            categories=list(reversed(categories)),
            locations=list(reversed(locations)),
            images=list(reversed(images)),
            price="50000.00",
            date_modified_gmt="2026-08-20T11:30:00+03:00",
            owner_contact_hidden=False,
            email="synthetic@example.invalid",
        )
        second = asyncio.run(
            CatalogueSyncService(session, FakeSource([equivalent])).run(
                "gate5a-canonical-equivalent"
            )
        )
        assert second.counts.items_unchanged == 1

        changed = equivalent.model_copy(update={"latitude": 1})
        third = asyncio.run(
            CatalogueSyncService(session, FakeSource([changed])).run("gate5a-canonical-changed")
        )
        assert third.counts.items_updated == 1

        listing_count = session.scalar(
            select(func.count()).select_from(Listing).where(Listing.external_id == "900001")
        )
        assert listing_count == 1
        assert session.scalar(select(func.count()).select_from(ListingSourcePayload)) == 1
        assert session.scalar(select(func.count()).select_from(ListingMedia)) == 2
        assert session.scalar(select(func.count()).select_from(ListingContact)) == 1
        assert session.scalar(select(func.count()).select_from(ListingCategory)) == 1
        assert session.scalar(select(func.count()).select_from(ListingLocation)) == 1
