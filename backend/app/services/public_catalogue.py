"""Public catalogue policy, normalization, and response construction."""

import math
import re
from uuid import UUID

from app.repositories.public_catalogue import (
    ListingFilters,
    ListingProjection,
    PublicCatalogueRepository,
)
from app.schemas.public_catalogue import (
    CategoryResponse,
    ListingDetailResponse,
    ListingPageResponse,
    ListingSummaryResponse,
    LocationResponse,
    MarketplaceResponse,
    PublicImage,
    TaxonomyLabel,
)

SUMMARY_LIMIT = 500
DESCRIPTION_LIMIT = 10_000
ALT_TEXT_LIMIT = 500


class PublicListingNotFound(LookupError):
    """The requested record is not publicly visible."""


def normalize_search(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip()
    if not 2 <= len(normalized) <= 100:
        raise ValueError("search must contain between 2 and 100 characters")
    return normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def public_slug(value: str, listing_id: UUID) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:80]
    return f"{slug or 'listing'}-{str(listing_id)[:8]}"


class PublicCatalogueService:
    def __init__(self, repository: PublicCatalogueRepository) -> None:
        self.repository = repository

    def marketplaces(self) -> list[MarketplaceResponse]:
        return [
            MarketplaceResponse(code=code, name=name, listing_count=count)
            for code, name, count in self.repository.marketplaces()
        ]

    def categories(self, marketplace: str | None) -> list[CategoryResponse]:
        return [
            CategoryResponse(
                code=code,
                name=name,
                marketplace=marketplace_code,
                parent=parent,
                listing_count=count,
            )
            for code, name, marketplace_code, parent, count in self.repository.categories(
                marketplace
            )
        ]

    def locations(self) -> list[LocationResponse]:
        rows = self.repository.locations()
        children: dict[UUID | None, list[UUID]] = {}
        records = {row[0]: row for row in rows}
        for identifier, parent_id, *_ in rows:
            children.setdefault(parent_id, []).append(identifier)

        def build(identifier: UUID) -> LocationResponse:
            _, parent_id, code, name, direct_count = records[identifier]
            child_models = [build(child) for child in children.get(identifier, [])]
            return LocationResponse(
                code=code,
                name=name,
                parent=records[parent_id][2] if parent_id in records else None,
                listing_count=direct_count + sum(item.listing_count for item in child_models),
                children=child_models,
            )

        return [build(identifier) for identifier in children.get(None, [])]

    def listings(self, filters: ListingFilters) -> ListingPageResponse:
        total, rows = self.repository.listings(filters)
        total_pages = math.ceil(total / filters.per_page) if total else 0
        return ListingPageResponse(
            items=[self._summary(row) for row in rows],
            page=filters.page,
            per_page=filters.per_page,
            total=total,
            total_pages=total_pages,
            has_next=filters.page < total_pages,
            has_previous=filters.page > 1,
        )

    def listing(self, listing_id: UUID) -> ListingDetailResponse:
        row = self.repository.listing(listing_id)
        if row is None:
            raise PublicListingNotFound
        summary = self._summary(row)
        categories = [
            TaxonomyLabel(code=code, name=name)
            for code, name in self.repository.listing_categories(listing_id)
        ]
        locations = [
            TaxonomyLabel(code=code, name=name)
            for _, _, code, name in self.repository.listing_locations(listing_id)
        ]
        gallery = [
            PublicImage(url=url, alt_text=(alt or "")[:ALT_TEXT_LIMIT])
            for url, alt in self.repository.listing_media(listing_id)
            if url.lower().startswith("https://")
        ]
        return ListingDetailResponse(
            **summary.model_dump(),
            description=(row.description or "")[:DESCRIPTION_LIMIT],
            tagline=(row.tagline or "")[:SUMMARY_LIMIT] or None,
            gallery=gallery,
            categories=categories,
            location_hierarchy=locations,
            source_modified_at=row.source_modified_at,
        )

    @staticmethod
    def _summary(row: ListingProjection) -> ListingSummaryResponse:
        image = None
        if row.primary_image_url and row.primary_image_url.lower().startswith("https://"):
            image = PublicImage(
                url=row.primary_image_url,
                alt_text=(row.primary_image_alt or "")[:ALT_TEXT_LIMIT],
            )
        location = None
        if row.location_code is not None and row.location_name is not None:
            location = TaxonomyLabel(code=row.location_code, name=row.location_name)
        return ListingSummaryResponse(
            id=row.id,
            title=row.title,
            slug=public_slug(row.title, row.id),
            summary=row.summary[:SUMMARY_LIMIT],
            marketplace=TaxonomyLabel(code=row.marketplace_code, name=row.marketplace_name),
            primary_category=TaxonomyLabel(code=row.category_code, name=row.category_name),
            location=location,
            price=row.price,
            currency=row.currency,
            pricing_type=row.pricing_type,
            featured=row.featured,
            rating=row.rating,
            rating_count=row.rating_count,
            primary_image=image,
            contact_available=row.contact_available,
            source_url=row.source_url if row.source_url.lower().startswith("https://") else None,
        )
