"""Internal normalized and public catalogue schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl


class TaxonomyRef(BaseModel):
    external_id: int
    name: str
    slug: str | None = None


class CanonicalMapping(BaseModel):
    marketplace_code: str
    marketplace_name: str
    category_code: str
    category_name: str


class NormalizedMedia(BaseModel):
    external_id: int
    url: HttpUrl
    alt_text: str
    position: int


class NormalizedContact(BaseModel):
    contact_type: Literal["email", "phone", "phone_2", "fax", "website"]
    value: str


class NormalizedListing(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_system: Literal["directorist"] = "directorist"
    external_id: int
    title: str
    slug: str
    source_url: HttpUrl
    source_status: str
    source_created_at: datetime | None
    source_modified_at: datetime | None
    directory_external_id: int | None
    source_author_id: int | None
    categories: list[TaxonomyRef]
    locations: list[TaxonomyRef]
    canonical_mappings: list[CanonicalMapping]
    classification_status: Literal["mapped", "pending"]
    summary: str
    description: str
    tagline: str
    latitude: Decimal | None
    longitude: Decimal | None
    map_hidden: bool
    price: Decimal | None
    currency: None = None
    pricing_type: str | None
    price_range: str | None
    contacts: list[NormalizedContact]
    media: list[NormalizedMedia]
    featured: bool
    popular: bool
    is_new: bool
    average_rating: Decimal
    rating_count: int
    source_checksum: str
    unknown_source_fields: tuple[str, ...]


class PublicTaxonomy(BaseModel):
    code: str
    name: str


class PublicPricing(BaseModel):
    amount: Decimal | None
    currency: str | None
    pricing_type: str | None
    price_range: str | None


class ListingSummary(BaseModel):
    adapter_id: str
    title: str
    marketplace: PublicTaxonomy | None
    categories: list[PublicTaxonomy]
    locations: list[str]
    summary: str
    pricing: PublicPricing
    primary_image: NormalizedMedia | None
    rating: Decimal | None
    featured: bool
    contact_available: bool
    source_url: HttpUrl
    source_modified_at: datetime | None


class ListingDetail(ListingSummary):
    description: str
    tagline: str
    media: list[NormalizedMedia]
    contacts: list[NormalizedContact]
