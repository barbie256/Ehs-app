"""Typed source mappings and catalogue with revision-owned immutable DDL."""

from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_sources_and_catalogue"
down_revision = "0002_canonical_taxonomy"
branch_labels = None
depends_on = None


def uuid_id() -> sa.Column[object]:
    return cast(
        sa.Column[object],
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )


def timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        cast(
            sa.Column[object],
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        ),
        cast(
            sa.Column[object],
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "vendors",
        uuid_id(),
        sa.Column("source_system", sa.String(30), nullable=True),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("business_name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(20),
            server_default=sa.text("'unverified'"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "verification_status IN ('unverified','pending','verified','rejected')",
            name=op.f("ck_vendors_vendor_verification_status"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vendors"),
        sa.UniqueConstraint("slug", name="uq_vendors_slug"),
        sa.UniqueConstraint(
            "source_system", "external_id", name="uq_vendors_source_system_external_id"
        ),
    )
    op.create_table(
        "source_taxonomy_mappings",
        uuid_id(),
        sa.Column("source_system", sa.String(30), nullable=False),
        sa.Column("source_taxonomy", sa.String(20), nullable=False),
        sa.Column("source_external_id", sa.String(100), nullable=False),
        sa.Column("source_name_snapshot", sa.String(200), nullable=True),
        sa.Column("marketplace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "mapping_status", sa.String(20), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("mapping_reason", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "mapping_status IN ('pending','approved','rejected')",
            name=op.f("ck_source_taxonomy_mappings_mapping_status"),
        ),
        sa.CheckConstraint(
            "source_taxonomy IN ('directory','category','location')",
            name=op.f("ck_source_taxonomy_mappings_source_taxonomy_type"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name="fk_source_taxonomy_mappings_approved_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_source_taxonomy_mappings_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name="fk_source_taxonomy_mappings_location_id_locations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["marketplace_id"],
            ["marketplaces.id"],
            name="fk_source_taxonomy_mappings_marketplace_id_marketplaces",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_taxonomy_mappings"),
        sa.UniqueConstraint(
            "source_system",
            "source_taxonomy",
            "source_external_id",
            name="uq_source_taxonomy_mappings_source_system_source_taxono_2a26",
        ),
    )
    for column in ("approved_by_user_id", "category_id", "location_id", "marketplace_id"):
        op.create_index(
            f"ix_source_taxonomy_mappings_{column}", "source_taxonomy_mappings", [column]
        )
    op.create_table(
        "listings",
        uuid_id(),
        sa.Column("source_system", sa.String(30), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("marketplace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_status", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "classification_status",
            sa.String(20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("price_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column(
            "pricing_type", sa.String(20), server_default=sa.text("'unspecified'"), nullable=False
        ),
        sa.Column("featured", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("contacts_hidden", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column(
            "first_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *timestamps(),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "classification_status IN ('mapped','pending','rejected')",
            name=op.f("ck_listings_listing_classification_status"),
        ),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_listings_listing_currency_format"),
        ),
        sa.CheckConstraint(
            "marketplace_id IS NOT NULL OR classification_status = 'pending'",
            name=op.f("ck_listings_listing_marketplace_classification"),
        ),
        sa.CheckConstraint(
            "price_amount IS NULL OR price_amount >= 0",
            name=op.f("ck_listings_listing_price_nonnegative"),
        ),
        sa.CheckConstraint(
            "pricing_type IN ('fixed','range','starting_at','contact','unspecified')",
            name=op.f("ck_listings_listing_pricing_type"),
        ),
        sa.CheckConstraint(
            "status IN ('active','unavailable','archived')", name=op.f("ck_listings_listing_status")
        ),
        sa.ForeignKeyConstraint(
            ["marketplace_id"],
            ["marketplaces.id"],
            name="fk_listings_marketplace_id_marketplaces",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["vendors.id"], name="fk_listings_vendor_id_vendors", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_listings"),
        sa.UniqueConstraint(
            "source_system", "external_id", name="uq_listings_source_system_external_id"
        ),
    )
    op.create_index("ix_listings_marketplace_id", "listings", ["marketplace_id"])
    op.create_index("ix_listings_vendor_id", "listings", ["vendor_id"])
    op.create_table(
        "listing_categories",
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("mapping_source", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_listing_categories_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name="fk_listing_categories_listing_id_listings",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("listing_id", "category_id", name="pk_listing_categories"),
    )
    op.create_index("ix_listing_categories_category_id", "listing_categories", ["category_id"])
    op.create_index(
        "uq_listing_categories_primary",
        "listing_categories",
        ["listing_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )
    op.create_table(
        "listing_locations",
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name="fk_listing_locations_listing_id_listings",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name="fk_listing_locations_location_id_locations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("listing_id", "location_id", name="pk_listing_locations"),
    )
    op.create_index("ix_listing_locations_location_id", "listing_locations", ["location_id"])
    op.create_index(
        "uq_listing_locations_primary",
        "listing_locations",
        ["listing_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )
    op.create_table(
        "listing_media",
        uuid_id(),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(30), nullable=False),
        sa.Column("source_external_id", sa.String(100), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("alt_text", sa.String(500), nullable=True),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("source_checksum", sa.String(64), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "media_type IN ('image','video')", name=op.f("ck_listing_media_media_type")
        ),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_listing_media_media_position_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name="fk_listing_media_listing_id_listings",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_listing_media"),
        sa.UniqueConstraint(
            "listing_id",
            "source_system",
            "source_external_id",
            name="uq_listing_media_listing_id_source_system_source_external_id",
        ),
    )
    op.create_index("ix_listing_media_listing_id", "listing_media", ["listing_id"])
    op.create_table(
        "listing_contacts",
        uuid_id(),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_type", sa.String(20), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("display_value", sa.Text(), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source_field", sa.String(50), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "contact_type IN ('email','phone','phone_2','website','fax')",
            name=op.f("ck_listing_contacts_contact_type"),
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name="fk_listing_contacts_listing_id_listings",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_listing_contacts"),
        sa.UniqueConstraint(
            "listing_id",
            "contact_type",
            "normalized_value",
            name="uq_listing_contacts_listing_id_contact_type_normalized_value",
        ),
    )
    op.create_index("ix_listing_contacts_listing_id", "listing_contacts", ["listing_id"])
    op.create_table(
        "listing_source_payloads",
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(30), nullable=False),
        sa.Column("sanitized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_checksum", sa.String(64), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name="fk_listing_source_payloads_listing_id_listings",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("listing_id", name="pk_listing_source_payloads"),
    )


def downgrade() -> None:
    op.drop_table("listing_source_payloads")
    op.drop_index("ix_listing_contacts_listing_id", table_name="listing_contacts")
    op.drop_table("listing_contacts")
    op.drop_index("ix_listing_media_listing_id", table_name="listing_media")
    op.drop_table("listing_media")
    op.drop_index("uq_listing_locations_primary", table_name="listing_locations")
    op.drop_index("ix_listing_locations_location_id", table_name="listing_locations")
    op.drop_table("listing_locations")
    op.drop_index("uq_listing_categories_primary", table_name="listing_categories")
    op.drop_index("ix_listing_categories_category_id", table_name="listing_categories")
    op.drop_table("listing_categories")
    op.drop_index("ix_listings_vendor_id", table_name="listings")
    op.drop_index("ix_listings_marketplace_id", table_name="listings")
    op.drop_table("listings")
    for column in ("marketplace_id", "location_id", "category_id", "approved_by_user_id"):
        op.drop_index(
            f"ix_source_taxonomy_mappings_{column}", table_name="source_taxonomy_mappings"
        )
    op.drop_table("source_taxonomy_mappings")
    op.drop_table("vendors")
