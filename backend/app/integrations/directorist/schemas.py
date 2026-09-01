"""Tolerant-but-observable Directorist v1 source schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, HttpUrl


def empty_to_none(value: object) -> object:
    return None if value == "" else value


OptionalDate = Annotated[datetime | None, BeforeValidator(empty_to_none)]
OptionalHttpUrl = Annotated[HttpUrl | None, BeforeValidator(empty_to_none)]


class SourceModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    @property
    def unknown_field_names(self) -> tuple[str, ...]:
        return tuple(sorted((self.model_extra or {}).keys()))


class SourceTaxonomy(SourceModel):
    id: int = Field(gt=0)
    name: str
    slug: str | None = None


class SourceImage(SourceModel):
    id: int = Field(gt=0)
    name: str | None = None
    src: HttpUrl
    alt: str | None = None
    position: int = Field(default=0, ge=0)
    date_created: OptionalDate = None
    date_created_gmt: OptionalDate = None
    date_modified: OptionalDate = None
    date_modified_gmt: OptionalDate = None


class DirectoristListingV1(SourceModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    permalink: HttpUrl
    status: str = Field(min_length=1)
    date_created: OptionalDate = None
    date_created_gmt: OptionalDate = None
    date_modified: OptionalDate = None
    date_modified_gmt: OptionalDate = None
    date_expired: OptionalDate = None
    description: str | None = None
    short_description: str | None = None
    tagline: str | None = None
    author: int | None = None
    directory: int | None = None
    categories: list[SourceTaxonomy] = Field(default_factory=list)
    locations: list[SourceTaxonomy] = Field(default_factory=list)
    tags: list[SourceTaxonomy] = Field(default_factory=list)
    address: str | None = None
    zip: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    map_hidden: bool = False
    price: Decimal | None = None
    price_range: str | None = None
    pricing_type: str | None = None
    email: str | None = None
    phone: str | None = None
    phone_2: str | None = None
    fax: str | None = None
    website: OptionalHttpUrl = None
    video_url: OptionalHttpUrl = None
    social_links: list[dict[str, Any]] | dict[str, Any] | None = None
    owner_contact_hidden: bool = True
    images: list[SourceImage] = Field(default_factory=list)
    featured: bool = False
    popular: bool = False
    new: bool = False
    never_expired: bool = False
    reviews_allowed: bool = False
    average_rating: Decimal = Decimal(0)
    rating_count: int = Field(default=0, ge=0)
    views_count: int = Field(default=0, ge=0)
    menu_order: int = 0
    plan: int | None = None
    related_ids: list[int] = Field(default_factory=list)
    links: dict[str, Any] | None = Field(default=None, alias="_links")


class DirectoristPage(BaseModel):
    items: list[DirectoristListingV1]
    current_page: int
    page_size: int
    total_items: int
    total_pages: int
    next_page: int | None


class ListingValidationFailure(BaseModel):
    """Safe identity for one invalid collection member; never contains source values."""

    external_id: str
    error_code: str = "invalid_listing_schema"
    field_summary: str = "listing"


class DirectoristValidatedPage(BaseModel):
    """A page whose malformed members are isolated for synchronization."""

    items: list[DirectoristListingV1]
    failures: list[ListingValidationFailure]
    current_page: int
    page_size: int
    total_items: int
    total_pages: int
    next_page: int | None
