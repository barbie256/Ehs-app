"""Typed source mapping and normalized catalogue models."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    source_system: Mapped[str | None] = mapped_column(String(30))
    external_id: Mapped[str | None] = mapped_column(String(100))
    business_name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    verification_status: Mapped[str] = mapped_column(
        String(20), server_default=text("'unverified'")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('unverified','pending','verified','rejected')",
            name="vendor_verification_status",
        ),
        UniqueConstraint("source_system", "external_id"),
    )


class SourceTaxonomyMapping(Base):
    __tablename__ = "source_taxonomy_mappings"
    __table_args__ = (
        UniqueConstraint("source_system", "source_taxonomy", "source_external_id"),
        CheckConstraint(
            "source_taxonomy IN ('directory','category','location')", name="source_taxonomy_type"
        ),
        CheckConstraint(
            "mapping_status IN ('pending','approved','rejected')", name="mapping_status"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    source_system: Mapped[str] = mapped_column(String(30))
    source_taxonomy: Mapped[str] = mapped_column(String(20))
    source_external_id: Mapped[str] = mapped_column(String(100))
    source_name_snapshot: Mapped[str | None] = mapped_column(String(200))
    marketplace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplaces.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    mapping_status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"))
    mapping_reason: Mapped[str | None] = mapped_column(Text)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source_system", "external_id"),
        CheckConstraint("status IN ('active','unavailable','archived')", name="listing_status"),
        CheckConstraint(
            "classification_status IN ('mapped','pending','rejected')",
            name="listing_classification_status",
        ),
        CheckConstraint(
            "marketplace_id IS NOT NULL OR classification_status = 'pending'",
            name="listing_marketplace_classification",
        ),
        CheckConstraint(
            "price_amount IS NULL OR price_amount >= 0", name="listing_price_nonnegative"
        ),
        CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="listing_currency_format"
        ),
        CheckConstraint(
            "pricing_type IN ('fixed','range','starting_at','contact','unspecified')",
            name="listing_pricing_type",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    source_system: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(100))
    marketplace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplaces.id", ondelete="RESTRICT"), index=True
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    source_status: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    classification_status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"))
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    pricing_type: Mapped[str] = mapped_column(String(20), server_default=text("'unspecified'"))
    featured: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    contacts_hidden: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    source_url: Mapped[str] = mapped_column(Text)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_checksum: Mapped[str] = mapped_column(String(64))
    first_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ListingCategory(Base):
    __tablename__ = "listing_categories"
    __table_args__ = (
        Index(
            "uq_listing_categories_primary",
            "listing_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    mapping_source: Mapped[str] = mapped_column(String(30))


class ListingLocation(Base):
    __tablename__ = "listing_locations"
    __table_args__ = (
        Index(
            "uq_listing_locations_primary",
            "listing_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class ListingMedia(Base):
    __tablename__ = "listing_media"
    __table_args__ = (
        UniqueConstraint("listing_id", "source_system", "source_external_id"),
        CheckConstraint("position >= 0", name="media_position_nonnegative"),
        CheckConstraint("media_type IN ('image','video')", name="media_type"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    source_system: Mapped[str] = mapped_column(String(30))
    source_external_id: Mapped[str] = mapped_column(String(100))
    source_url: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String(20))
    alt_text: Mapped[str | None] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    source_checksum: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ListingContact(Base):
    __tablename__ = "listing_contacts"
    __table_args__ = (
        CheckConstraint(
            "contact_type IN ('email','phone','phone_2','website','fax')", name="contact_type"
        ),
        UniqueConstraint("listing_id", "contact_type", "normalized_value"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    contact_type: Mapped[str] = mapped_column(String(20))
    normalized_value: Mapped[str] = mapped_column(Text)
    display_value: Mapped[str] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    source_field: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ListingSourcePayload(Base):
    """One latest sanitized payload per listing; no payload history."""

    __tablename__ = "listing_source_payloads"
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    schema_version: Mapped[str] = mapped_column(String(30))
    sanitized_payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    payload_checksum: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
