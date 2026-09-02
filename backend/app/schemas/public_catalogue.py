"""Explicit public catalogue API contracts."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaxonomyLabel(PublicModel):
    code: str
    name: str


class MarketplaceResponse(TaxonomyLabel):
    listing_count: int = Field(ge=0)


class CategoryResponse(TaxonomyLabel):
    marketplace: str
    parent: str | None
    listing_count: int = Field(ge=0)


class LocationResponse(TaxonomyLabel):
    parent: str | None
    listing_count: int = Field(ge=0)
    children: list[LocationResponse]


class PublicImage(PublicModel):
    url: str = Field(pattern=r"^https://")
    alt_text: str


class ListingSummaryResponse(PublicModel):
    id: UUID
    title: str
    slug: str
    summary: str
    marketplace: TaxonomyLabel
    primary_category: TaxonomyLabel
    location: TaxonomyLabel | None
    price: Decimal | None
    currency: str | None
    pricing_type: str
    featured: bool
    rating: Decimal | None
    rating_count: int = Field(ge=0)
    primary_image: PublicImage | None
    contact_available: bool
    source_url: str | None = Field(default=None, pattern=r"^https://")


class ListingDetailResponse(ListingSummaryResponse):
    description: str
    tagline: str | None
    gallery: list[PublicImage]
    categories: list[TaxonomyLabel]
    location_hierarchy: list[TaxonomyLabel]
    source_modified_at: datetime | None


class ListingPageResponse(PublicModel):
    items: list[ListingSummaryResponse]
    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class ListingOrderBy(StrEnum):
    NEWEST = "newest"
    TITLE = "title"
    RATING = "rating"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"
