"""Versioned canonical checksum contract for normalized Directorist source content."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

from app.schemas.catalogue import NormalizedContact, NormalizedListing

SOURCE_CHECKSUM_VERSION = 2

SOURCE_CHECKSUM_INCLUDED_FIELDS = frozenset(
    {
        "source_system",
        "external_id",
        "title",
        "slug",
        "source_url",
        "source_status",
        "source_created_at",
        "source_modified_at",
        "directory_external_id",
        "categories",
        "locations",
        "summary",
        "description",
        "tagline",
        "latitude",
        "longitude",
        "map_hidden",
        "owner_contact_hidden",
        "price",
        "currency",
        "pricing_type",
        "price_range",
        "contacts",
        "media",
        "featured",
        "popular",
        "is_new",
        "average_rating",
        "rating_count",
    }
)

SOURCE_CHECKSUM_EXCLUDED_FIELDS = frozenset(
    {
        "canonical_mappings",
        "classification_status",
        "source_author_id",
        "source_checksum",
        "unknown_source_fields",
    }
)


def calculate_source_checksum(listing: NormalizedListing) -> str:
    """Hash canonical source-owned state without database or resolver-derived identity."""
    material = {
        "version": SOURCE_CHECKSUM_VERSION,
        "source_system": listing.source_system,
        "external_id": listing.external_id,
        "title": listing.title,
        "slug": listing.slug,
        "source_url": str(listing.source_url),
        "source_status": listing.source_status,
        "source_created_at": _canonical_datetime(listing.source_created_at),
        "source_modified_at": _canonical_datetime(listing.source_modified_at),
        "directory_external_id": listing.directory_external_id,
        "categories": sorted(
            (item.model_dump(mode="json") for item in listing.categories),
            key=lambda item: (item["external_id"], item["slug"] or "", item["name"]),
        ),
        "locations": sorted(
            (item.model_dump(mode="json") for item in listing.locations),
            key=lambda item: (item["external_id"], item["slug"] or "", item["name"]),
        ),
        "summary": listing.summary,
        "description": listing.description,
        "tagline": listing.tagline,
        "latitude": _canonical_decimal(listing.latitude),
        "longitude": _canonical_decimal(listing.longitude),
        "map_hidden": listing.map_hidden,
        "owner_contact_hidden": listing.owner_contact_hidden,
        "price": _canonical_decimal(listing.price),
        "currency": listing.currency,
        "pricing_type": listing.pricing_type,
        "price_range": listing.price_range,
        "contacts": sorted(
            (
                {
                    "contact_type": item.contact_type,
                    "value": _canonical_contact_value(item),
                }
                for item in listing.contacts
            ),
            key=lambda item: (item["contact_type"], item["value"]),
        ),
        "media": sorted(
            (item.model_dump(mode="json") for item in listing.media),
            key=lambda item: (
                item["position"],
                item["external_id"],
                item["url"],
                item["alt_text"],
            ),
        ),
        "featured": listing.featured,
        "popular": listing.popular,
        "is_new": listing.is_new,
        "average_rating": _canonical_decimal(listing.average_rating),
        "rating_count": listing.rating_count,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _canonical_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "0"
    normalized = format(value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def _canonical_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return "naive:" + value.isoformat(timespec="auto")
    canonical = value.astimezone(UTC).isoformat(timespec="auto")
    return "utc:" + canonical.replace("+00:00", "Z")


def _canonical_contact_value(contact: NormalizedContact) -> str:
    value = contact.value.strip()
    return value.casefold() if contact.contact_type in {"email", "website"} else value
