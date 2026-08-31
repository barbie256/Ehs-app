"""Pure Directorist normalization; no database or network dependencies."""

import json
from hashlib import sha256
from typing import Protocol

import nh3

from app.integrations.directorist.errors import DirectoristMappingError, DirectoristSchemaError
from app.integrations.directorist.schemas import DirectoristListingV1
from app.schemas.catalogue import (
    CanonicalMapping,
    ListingDetail,
    ListingSummary,
    NormalizedContact,
    NormalizedListing,
    NormalizedMedia,
    PublicPricing,
    PublicTaxonomy,
    TaxonomyRef,
)

ALLOWED_TAGS = {"p", "br", "strong", "em", "ul", "ol", "li", "a"}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}
ALLOWED_SCHEMES = {"http", "https"}
SUMMARY_LIMIT = 500


class TaxonomyResolver(Protocol):
    def resolve_category(self, external_id: int) -> CanonicalMapping | None: ...


def sanitize_html(value: str | None) -> str:
    return nh3.clean(
        value or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_SCHEMES,
        clean_content_tags={"script", "style", "iframe", "form"},
    )


def plain_text(value: str | None, *, limit: int = SUMMARY_LIMIT) -> str:
    return nh3.clean_text(sanitize_html(value))[:limit].strip()


def map_listing(source: DirectoristListingV1, resolver: TaxonomyResolver) -> NormalizedListing:
    if source.latitude is not None and not -90 <= source.latitude <= 90:
        raise DirectoristSchemaError("source latitude is outside the permitted range")
    if source.longitude is not None and not -180 <= source.longitude <= 180:
        raise DirectoristSchemaError("source longitude is outside the permitted range")

    mappings = [
        mapping for item in source.categories if (mapping := resolver.resolve_category(item.id))
    ]
    marketplaces = {mapping.marketplace_code for mapping in mappings}
    if len(marketplaces) > 1:
        raise DirectoristMappingError("source categories resolve to incompatible marketplaces")

    contacts: list[NormalizedContact] = []
    if not source.owner_contact_hidden:
        for contact_type in ("email", "phone", "phone_2", "fax", "website"):
            raw = getattr(source, contact_type)
            if raw:
                contacts.append(
                    NormalizedContact(contact_type=contact_type, value=str(raw).strip())
                )

    media = [
        NormalizedMedia(
            external_id=item.id,
            url=item.src,
            alt_text=plain_text(item.alt, limit=300),
            position=item.position,
        )
        for item in sorted(source.images, key=lambda image: (image.position, image.id))
    ]
    categories = [
        TaxonomyRef(external_id=item.id, name=item.name, slug=item.slug)
        for item in source.categories
    ]
    locations = [
        TaxonomyRef(external_id=item.id, name=item.name, slug=item.slug)
        for item in source.locations
    ]
    checksum_input = {
        "external_id": source.id,
        "title": source.name.strip(),
        "slug": source.slug,
        "source_url": str(source.permalink),
        "status": source.status,
        "modified": source.date_modified_gmt.isoformat() if source.date_modified_gmt else None,
        "categories": [item.model_dump(mode="json") for item in categories],
        "locations": [item.model_dump(mode="json") for item in locations],
        "summary": plain_text(source.short_description),
        "description": sanitize_html(source.description),
        "tagline": plain_text(source.tagline, limit=200),
        "price": str(source.price) if source.price is not None else None,
        "pricing_type": source.pricing_type,
        "media": [item.model_dump(mode="json") for item in media],
        "contacts": [item.model_dump(mode="json") for item in contacts],
    }
    checksum = sha256(
        json.dumps(checksum_input, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return NormalizedListing(
        external_id=source.id,
        title=source.name.strip(),
        slug=source.slug,
        source_url=source.permalink,
        source_status=source.status,
        source_created_at=source.date_created_gmt or source.date_created,
        source_modified_at=source.date_modified_gmt or source.date_modified,
        directory_external_id=source.directory,
        source_author_id=source.author,
        categories=categories,
        locations=locations,
        canonical_mappings=mappings,
        classification_status="mapped" if mappings else "pending",
        summary=plain_text(source.short_description),
        description=sanitize_html(source.description),
        tagline=plain_text(source.tagline, limit=200),
        latitude=source.latitude,
        longitude=source.longitude,
        map_hidden=source.map_hidden,
        price=source.price,
        pricing_type=source.pricing_type,
        price_range=source.price_range,
        contacts=contacts,
        media=media,
        featured=source.featured,
        popular=source.popular,
        is_new=source.new,
        average_rating=source.average_rating,
        rating_count=source.rating_count,
        source_checksum=checksum,
        unknown_source_fields=source.unknown_field_names,
    )


def to_summary(listing: NormalizedListing) -> ListingSummary:
    first = listing.canonical_mappings[0] if listing.canonical_mappings else None
    return ListingSummary(
        adapter_id=f"directorist:{listing.external_id}",
        title=listing.title,
        marketplace=PublicTaxonomy(code=first.marketplace_code, name=first.marketplace_name)
        if first
        else None,
        categories=[
            PublicTaxonomy(code=item.category_code, name=item.category_name)
            for item in listing.canonical_mappings
        ],
        locations=[item.name for item in listing.locations],
        summary=listing.summary,
        pricing=PublicPricing(
            amount=listing.price,
            currency=None,
            pricing_type=listing.pricing_type,
            price_range=listing.price_range,
        ),
        primary_image=listing.media[0] if listing.media else None,
        rating=listing.average_rating if listing.rating_count > 0 else None,
        featured=listing.featured,
        contact_available=bool(listing.contacts),
        source_url=listing.source_url,
        source_modified_at=listing.source_modified_at,
    )


def to_detail(listing: NormalizedListing) -> ListingDetail:
    return ListingDetail(
        **to_summary(listing).model_dump(),
        description=listing.description,
        tagline=listing.tagline,
        media=listing.media,
        contacts=listing.contacts,
    )
