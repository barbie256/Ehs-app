"""Read-only, projection-based public catalogue queries."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, case, cast, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import NUMERIC
from sqlalchemy.orm import Session, aliased

from app.db.models.catalogue import (
    Listing,
    ListingCategory,
    ListingContact,
    ListingLocation,
    ListingMedia,
    ListingSourcePayload,
)
from app.db.models.taxonomy import Category, Location, Marketplace
from app.schemas.public_catalogue import ListingOrderBy, SortOrder


@dataclass(frozen=True)
class ListingFilters:
    page: int
    per_page: int
    marketplace: str | None = None
    category: str | None = None
    location_ids: tuple[UUID, ...] | None = None
    search: str | None = None
    featured: bool | None = None
    order_by: ListingOrderBy = ListingOrderBy.NEWEST
    order: SortOrder = SortOrder.DESC


@dataclass(frozen=True)
class ListingProjection:
    id: UUID
    title: str
    summary: str
    marketplace_code: str
    marketplace_name: str
    category_code: str
    category_name: str
    location_code: str | None
    location_name: str | None
    price: Decimal | None
    currency: str | None
    pricing_type: str
    featured: bool
    rating: Decimal | None
    rating_count: int
    primary_image_url: str | None
    primary_image_alt: str | None
    contact_available: bool
    source_url: str
    description: str | None
    tagline: str | None
    source_modified_at: datetime | None


class PublicCatalogueRepository:
    """Caller-transactional public queries which never return ORM entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def visible_listing_ids() -> Select[tuple[UUID]]:
        primary = aliased(ListingCategory)
        primary_category = aliased(Category)
        return (
            select(Listing.id)
            .join(Marketplace, Marketplace.id == Listing.marketplace_id)
            .join(primary, and_(primary.listing_id == Listing.id, primary.is_primary.is_(True)))
            .join(
                primary_category,
                and_(
                    primary_category.id == primary.category_id,
                    primary_category.marketplace_id == Listing.marketplace_id,
                    primary_category.is_active.is_(True),
                ),
            )
            .where(
                Listing.status == "active",
                Listing.archived_at.is_(None),
                Listing.classification_status == "mapped",
                Listing.marketplace_id.is_not(None),
                Marketplace.is_active.is_(True),
            )
        )

    def marketplaces(self) -> list[tuple[str, str, int]]:
        visible = self.visible_listing_ids().subquery()
        count = func.count(func.distinct(visible.c.id))
        order = case(
            (Marketplace.code == "property", 0),
            (Marketplace.code == "construction", 1),
            (Marketplace.code == "home_interior", 2),
            (Marketplace.code == "professional_services", 3),
            else_=4,
        )
        rows = self.session.execute(
            select(Marketplace.code, Marketplace.name, count)
            .outerjoin(Listing, Listing.marketplace_id == Marketplace.id)
            .outerjoin(visible, visible.c.id == Listing.id)
            .where(Marketplace.is_active.is_(True))
            .group_by(Marketplace.id)
            .order_by(order, Marketplace.name, Marketplace.code)
        )
        return [(code, name, int(total)) for code, name, total in rows]

    def categories(self, marketplace: str | None) -> list[tuple[str, str, str, str | None, int]]:
        parent = aliased(Category)
        visible = self.visible_listing_ids().subquery()
        statement = (
            select(
                Category.code,
                Category.name,
                Marketplace.code,
                parent.code,
                func.count(func.distinct(visible.c.id)),
            )
            .join(Marketplace, Marketplace.id == Category.marketplace_id)
            .outerjoin(parent, and_(parent.id == Category.parent_id, parent.is_active.is_(True)))
            .outerjoin(ListingCategory, ListingCategory.category_id == Category.id)
            .outerjoin(visible, visible.c.id == ListingCategory.listing_id)
            .where(Category.is_active.is_(True), Marketplace.is_active.is_(True))
            .group_by(Category.id, Marketplace.code, Marketplace.sort_order, parent.code)
            .order_by(Marketplace.sort_order, Marketplace.code, Category.name, Category.code)
        )
        if marketplace is not None:
            statement = statement.where(Marketplace.code == marketplace)
        return [(a, b, c, d, int(e)) for a, b, c, d, e in self.session.execute(statement)]

    def locations(self) -> list[tuple[UUID, UUID | None, str, str, int]]:
        visible = self.visible_listing_ids().subquery()
        rows = self.session.execute(
            select(
                Location.id,
                Location.parent_id,
                Location.slug,
                Location.name,
                func.count(func.distinct(visible.c.id)),
            )
            .outerjoin(ListingLocation, ListingLocation.location_id == Location.id)
            .outerjoin(visible, visible.c.id == ListingLocation.listing_id)
            .where(Location.is_active.is_(True))
            .group_by(Location.id)
            .order_by(Location.name, Location.slug)
        )
        return [(a, b, c, d, int(e)) for a, b, c, d, e in rows]

    def location_descendants(self, code: str) -> tuple[UUID, ...]:
        rows = self.session.execute(
            select(Location.id, Location.parent_id, Location.slug).where(
                Location.is_active.is_(True)
            )
        ).all()
        matches = [row.id for row in rows if row.slug == code]
        if len(matches) != 1:
            return ()
        selected = set(matches)
        changed = True
        while changed:
            before = len(selected)
            selected.update(row.id for row in rows if row.parent_id in selected)
            changed = len(selected) != before
        return tuple(sorted(selected, key=str))

    def listings(self, filters: ListingFilters) -> tuple[int, list[ListingProjection]]:
        statement = self._listing_statement(filters)
        total = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        paged = statement.offset((filters.page - 1) * filters.per_page).limit(filters.per_page)
        return total, [ListingProjection(*row) for row in self.session.execute(paged)]

    def listing(self, listing_id: UUID) -> ListingProjection | None:
        row = self.session.execute(
            self._listing_statement(ListingFilters(1, 1)).where(Listing.id == listing_id)
        ).one_or_none()
        return ListingProjection(*row) if row is not None else None

    def listing_categories(self, listing_id: UUID) -> list[tuple[str, str]]:
        return [
            (code, name)
            for code, name in self.session.execute(
                select(Category.code, Category.name)
                .join(ListingCategory, ListingCategory.category_id == Category.id)
                .where(ListingCategory.listing_id == listing_id, Category.is_active.is_(True))
                .order_by(ListingCategory.is_primary.desc(), Category.name, Category.code)
            )
        ]

    def listing_locations(self, listing_id: UUID) -> list[tuple[UUID, UUID | None, str, str]]:
        linked = select(ListingLocation.location_id).where(ListingLocation.listing_id == listing_id)
        all_locations = self.session.execute(
            select(Location.id, Location.parent_id, Location.slug, Location.name).where(
                Location.is_active.is_(True)
            )
        ).all()
        linked_ids = set(self.session.scalars(linked))
        by_id = {row.id: row for row in all_locations}
        ordered: list[tuple[UUID, UUID | None, str, str]] = []
        for location_id in sorted(linked_ids, key=str):
            chain = []
            current = by_id.get(location_id)
            while current is not None:
                chain.append((current.id, current.parent_id, current.slug, current.name))
                current = by_id.get(current.parent_id)
            for item in reversed(chain):
                if item not in ordered:
                    ordered.append(item)
        return ordered

    def listing_media(self, listing_id: UUID) -> list[tuple[str, str | None]]:
        return [
            (url, alt)
            for url, alt in self.session.execute(
                select(ListingMedia.source_url, ListingMedia.alt_text)
                .where(ListingMedia.listing_id == listing_id, ListingMedia.media_type == "image")
                .order_by(ListingMedia.position, ListingMedia.id)
            )
        ]

    def _listing_statement(self, filters: ListingFilters) -> Select[tuple[object, ...]]:
        primary = aliased(ListingCategory)
        category = aliased(Category)
        primary_location = aliased(ListingLocation)
        location = aliased(Location)
        payload = aliased(ListingSourcePayload)
        image_url = (
            select(ListingMedia.source_url)
            .where(
                ListingMedia.listing_id == Listing.id,
                ListingMedia.media_type == "image",
                ListingMedia.source_url.startswith("https://"),
            )
            .order_by(ListingMedia.position, ListingMedia.id)
            .limit(1)
            .scalar_subquery()
        )
        image_alt = (
            select(ListingMedia.alt_text)
            .where(
                ListingMedia.listing_id == Listing.id,
                ListingMedia.media_type == "image",
                ListingMedia.source_url.startswith("https://"),
            )
            .order_by(ListingMedia.position, ListingMedia.id)
            .limit(1)
            .scalar_subquery()
        )
        rating_count = cast(payload.sanitized_payload["rating_count"].astext, NUMERIC)
        average_rating = cast(payload.sanitized_payload["average_rating"].astext, NUMERIC)
        statement = (
            select(
                Listing.id,
                Listing.title,
                func.coalesce(Listing.summary, literal("")),
                Marketplace.code,
                Marketplace.name,
                category.code,
                category.name,
                location.slug,
                location.name,
                Listing.price_amount,
                Listing.currency,
                Listing.pricing_type,
                Listing.featured,
                case((rating_count > 0, average_rating), else_=None),
                func.coalesce(rating_count, 0),
                image_url,
                image_alt,
                and_(
                    Listing.contacts_hidden.is_(False),
                    exists().where(
                        ListingContact.listing_id == Listing.id,
                        ListingContact.is_public.is_(True),
                    ),
                ),
                Listing.source_url,
                Listing.description,
                payload.sanitized_payload["tagline"].astext,
                Listing.source_modified_at,
            )
            .join(Marketplace, Marketplace.id == Listing.marketplace_id)
            .join(primary, and_(primary.listing_id == Listing.id, primary.is_primary.is_(True)))
            .join(
                category,
                and_(
                    category.id == primary.category_id,
                    category.marketplace_id == Listing.marketplace_id,
                    category.is_active.is_(True),
                ),
            )
            .outerjoin(
                primary_location,
                and_(
                    primary_location.listing_id == Listing.id, primary_location.is_primary.is_(True)
                ),
            )
            .outerjoin(
                location,
                and_(location.id == primary_location.location_id, location.is_active.is_(True)),
            )
            .outerjoin(payload, payload.listing_id == Listing.id)
            .where(
                Listing.status == "active",
                Listing.archived_at.is_(None),
                Listing.classification_status == "mapped",
                Listing.marketplace_id.is_not(None),
                Marketplace.is_active.is_(True),
            )
        )
        if filters.marketplace is not None:
            statement = statement.where(Marketplace.code == filters.marketplace)
        if filters.category is not None:
            category_match = aliased(ListingCategory)
            category_value = aliased(Category)
            statement = statement.where(
                exists()
                .where(category_match.listing_id == Listing.id)
                .where(category_value.id == category_match.category_id)
                .where(category_value.code == filters.category, category_value.is_active.is_(True))
            )
        if filters.location_ids is not None:
            if not filters.location_ids:
                statement = statement.where(literal(False))
            else:
                statement = statement.where(
                    exists().where(
                        ListingLocation.listing_id == Listing.id,
                        ListingLocation.location_id.in_(filters.location_ids),
                    )
                )
        if filters.search is not None:
            pattern = f"%{filters.search}%"
            statement = statement.where(
                or_(
                    Listing.title.ilike(pattern, escape="\\"),
                    Listing.summary.ilike(pattern, escape="\\"),
                    Listing.description.ilike(pattern, escape="\\"),
                )
            )
        if filters.featured is not None:
            statement = statement.where(Listing.featured.is_(filters.featured))
        sort_expression = {
            ListingOrderBy.NEWEST: func.coalesce(Listing.source_modified_at, Listing.created_at),
            ListingOrderBy.TITLE: func.lower(Listing.title),
            ListingOrderBy.RATING: func.coalesce(average_rating, 0),
        }[filters.order_by]
        ordering = (
            sort_expression.asc() if filters.order is SortOrder.ASC else sort_expression.desc()
        )
        return statement.order_by(ordering, Listing.id.asc())
