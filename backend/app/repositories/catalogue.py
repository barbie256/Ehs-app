"""Caller-transactional persistence for Directorist-owned catalogue data."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.db.models.catalogue import (
    Listing,
    ListingCategory,
    ListingContact,
    ListingLocation,
    ListingMedia,
    ListingSourcePayload,
)
from app.repositories.taxonomy import ApprovedCategory
from app.schemas.catalogue import NormalizedListing
from app.services.taxonomy_resolver import DatabaseTaxonomyResolver


@dataclass(frozen=True)
class UpsertResult:
    outcome: str
    pending_mapping: bool


class CatalogueRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self, normalized: NormalizedListing, resolver: DatabaseTaxonomyResolver
    ) -> UpsertResult:
        now = datetime.now(UTC)
        listing = self.session.scalar(
            select(Listing).where(
                Listing.source_system == normalized.source_system,
                Listing.external_id == str(normalized.external_id),
            )
        )
        approved = [
            resolved
            for source in normalized.categories
            if (resolved := resolver.category(source.external_id)) is not None
        ]
        marketplace_ids = {item.marketplace_id for item in approved}
        if len(marketplace_ids) > 1:
            raise ValueError("classification_conflict")
        marketplace_id = approved[0].marketplace_id if approved else None
        classification = "mapped" if approved else "pending"
        if listing is not None and listing.source_checksum == normalized.source_checksum:
            listing.last_synced_at = now
            if listing.status == "unavailable" and normalized.source_status == "publish":
                listing.status = "active"
                listing.archived_at = None
            self.session.flush()
            return UpsertResult("unchanged", classification == "pending")

        values = dict(
            marketplace_id=marketplace_id,
            title=normalized.title,
            summary=normalized.summary or None,
            description=normalized.description or None,
            source_status=normalized.source_status,
            status="active" if normalized.source_status == "publish" else "unavailable",
            classification_status=classification,
            price_amount=normalized.price,
            currency=None,
            pricing_type=self._pricing_type(normalized.pricing_type),
            featured=normalized.featured,
            contacts_hidden=normalized.owner_contact_hidden,
            source_url=str(normalized.source_url),
            source_created_at=normalized.source_created_at,
            source_modified_at=normalized.source_modified_at,
            source_checksum=normalized.source_checksum,
            last_synced_at=now,
            updated_at=now,
            archived_at=None,
        )
        outcome = "updated"
        if listing is None:
            listing = Listing(
                source_system=normalized.source_system,
                external_id=str(normalized.external_id),
                **values,
            )
            self.session.add(listing)
            self.session.flush()
            outcome = "inserted"
        else:
            for key, value in values.items():
                setattr(listing, key, value)
            self.session.flush()

        self._replace_categories(listing, approved)
        self._replace_locations(listing, normalized, resolver)
        self._replace_media(listing, normalized)
        self._replace_contacts(listing, normalized)
        self._replace_payload(listing, normalized, now)
        self.session.flush()
        return UpsertResult(outcome, classification == "pending")

    def archive_unseen(self, observed_since: datetime) -> int:
        result = self.session.execute(
            update(Listing)
            .where(
                Listing.source_system == "directorist",
                Listing.last_synced_at < observed_since,
                Listing.status == "active",
            )
            .values(status="unavailable", archived_at=datetime.now(UTC))
        )
        assert isinstance(result, CursorResult)
        return int(result.rowcount or 0)

    def _replace_categories(self, listing: Listing, approved: list[ApprovedCategory]) -> None:
        self.session.execute(
            delete(ListingCategory).where(ListingCategory.listing_id == listing.id)
        )
        for index, item in enumerate(approved):
            self.session.add(
                ListingCategory(
                    listing_id=listing.id,
                    category_id=item.category_id,
                    is_primary=index == 0,
                    mapping_source="directorist",
                )
            )

    def _replace_locations(
        self,
        listing: Listing,
        normalized: NormalizedListing,
        resolver: DatabaseTaxonomyResolver,
    ) -> None:
        self.session.execute(
            delete(ListingLocation).where(ListingLocation.listing_id == listing.id)
        )
        location_ids = [
            resolved
            for source in normalized.locations
            if (resolved := resolver.location_id(source.external_id)) is not None
        ]
        for index, location_id in enumerate(dict.fromkeys(location_ids)):
            self.session.add(
                ListingLocation(
                    listing_id=listing.id, location_id=location_id, is_primary=index == 0
                )
            )

    def _replace_media(self, listing: Listing, normalized: NormalizedListing) -> None:
        self.session.execute(delete(ListingMedia).where(ListingMedia.listing_id == listing.id))
        for media in normalized.media:
            url = str(media.url)
            checksum = sha256(f"{media.external_id}|{url}|{media.alt_text}".encode()).hexdigest()
            self.session.add(
                ListingMedia(
                    listing_id=listing.id,
                    source_system="directorist",
                    source_external_id=str(media.external_id),
                    source_url=url,
                    media_type="image",
                    alt_text=media.alt_text or None,
                    position=media.position,
                    source_checksum=checksum,
                )
            )

    def _replace_contacts(self, listing: Listing, normalized: NormalizedListing) -> None:
        self.session.execute(delete(ListingContact).where(ListingContact.listing_id == listing.id))
        for contact in normalized.contacts:
            value = contact.value.strip()
            self.session.add(
                ListingContact(
                    listing_id=listing.id,
                    contact_type=contact.contact_type,
                    normalized_value=value.casefold()
                    if contact.contact_type in {"email", "website"}
                    else value,
                    display_value=value,
                    is_public=True,
                    source_field=contact.contact_type,
                )
            )

    def _replace_payload(
        self, listing: Listing, normalized: NormalizedListing, observed_at: datetime
    ) -> None:
        payload = normalized.model_dump(
            mode="json",
            exclude={"contacts", "unknown_source_fields", "canonical_mappings"},
        )
        if normalized.map_hidden:
            payload["latitude"] = None
            payload["longitude"] = None
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        current = self.session.get(ListingSourcePayload, listing.id)
        values = dict(
            schema_version="directorist-normalized-v1",
            sanitized_payload=payload,
            payload_checksum=sha256(payload_json.encode()).hexdigest(),
            observed_at=observed_at,
        )
        if current is None:
            self.session.add(ListingSourcePayload(listing_id=listing.id, **values))
        else:
            for key, value in values.items():
                setattr(current, key, value)

    @staticmethod
    def _pricing_type(value: str | None) -> str:
        mapping = {"price": "fixed", "price_range": "range", "contact": "contact"}
        return mapping.get(value or "", "unspecified")
