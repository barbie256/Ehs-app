"""Explicit idempotent canonical marketplace, category, and role seed."""

import os
import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.identity import Role
from app.db.models.taxonomy import Category, Location, Marketplace
from app.db.session import create_database_engine, session_scope, validate_development_url

MARKETPLACES = (
    ("property", "Property", "Sale, rental and development listings"),
    ("construction", "Construction", "Materials and construction supplies"),
    ("home_interior", "Home & Interior", "Home living, fittings, décor and appliances"),
    ("professional_services", "Professional Services", "Built-environment and home services"),
)
CATEGORY_NAMES = {
    "property": (
        "Homes for Sale",
        "Land & Plots",
        "Apartments",
        "Commercial Properties",
        "Rental Properties",
        "Estates",
        "Hotels",
        "New Developments",
    ),
    "construction": (
        "Cement",
        "Steel",
        "Bricks",
        "Roofing Materials",
        "Timber",
        "Plumbing Materials",
        "Electrical Supplies",
        "Hardware",
        "Paint",
        "Tiles",
        "Doors",
        "Windows",
        "Sanitary Ware",
        "Finishes",
        "Solar Systems",
        "Water Harvesting Solutions",
        "Smart Home Technologies",
        "Landscaping Products",
        "Energy-Efficient Building Materials",
        "Energy Solutions",
        "Building Materials",
    ),
    "home_interior": (
        "Furniture",
        "Kitchen Products",
        "Sanitary Ware",
        "Tiles",
        "Lighting",
        "Home Décor",
        "Appliances",
        "Electronics",
        "Kitchen Equipment",
    ),
    "professional_services": (
        "Architects",
        "Engineers",
        "Contractors",
        "Interior Designers",
        "Property Managers",
        "Movers",
        "Cleaning Services",
        "Quantity Surveyors",
    ),
}


@dataclass(frozen=True)
class LocationSeed:
    """Immutable Africa-ready location identity; code is stored in Location.slug."""

    code: str
    name: str
    parent_code: str | None
    country_code: str
    location_type: str


LOCATION_DEFINITIONS = (
    LocationSeed("africa", "Africa", None, "AF", "continent"),
    LocationSeed("uganda", "Uganda", "africa", "UG", "country"),
    LocationSeed("kampala", "Kampala", "uganda", "UG", "city"),
)
ROLES = (
    ("customer", "Customer"),
    ("vendor", "Vendor"),
    ("support", "Support"),
    ("content_manager", "Content Manager"),
    ("admin", "Administrator"),
)


class SeedConflictError(RuntimeError):
    """Stable identity is already owned by an incompatible record."""


def slugify(value: str) -> str:
    normalized = value.lower().replace("&", " and ").replace("é", "e")
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


@dataclass(frozen=True)
class SeedCounts:
    marketplaces: int
    categories: int
    locations: int
    roles: int


def validate_location_definitions(definitions: tuple[LocationSeed, ...]) -> None:
    """Reject missing parents and cycles before any seed rows are created."""
    by_code = {item.code: item for item in definitions}
    if len(by_code) != len(definitions):
        raise SeedConflictError("location stable codes must be unique")
    for item in definitions:
        seen = {item.code}
        parent_code = item.parent_code
        while parent_code is not None:
            if parent_code not in by_code:
                raise SeedConflictError("location parent stable code is missing")
            if parent_code in seen:
                raise SeedConflictError("location hierarchy contains a cycle")
            seen.add(parent_code)
            parent_code = by_code[parent_code].parent_code


def seed_canonical_taxonomy(session: Session) -> SeedCounts:
    """Insert missing stable identities, preserving edited display fields."""
    validate_location_definitions(LOCATION_DEFINITIONS)
    marketplace_by_code: dict[str, Marketplace] = {}
    for order, (code, name, description) in enumerate(MARKETPLACES):
        record = session.scalar(select(Marketplace).where(Marketplace.code == code))
        if record is None:
            record = Marketplace(code=code, name=name, description=description, sort_order=order)
            session.add(record)
            session.flush()
        marketplace_by_code[code] = record

    for marketplace_code, names in CATEGORY_NAMES.items():
        marketplace = marketplace_by_code[marketplace_code]
        for order, name in enumerate(names):
            slug = slugify(name)
            code = slug.replace("-", "_")
            by_code = session.scalar(
                select(Category).where(
                    Category.marketplace_id == marketplace.id, Category.code == code
                )
            )
            by_slug = session.scalar(
                select(Category).where(
                    Category.marketplace_id == marketplace.id, Category.slug == slug
                )
            )
            if by_code is not None and by_code.slug != slug:
                raise SeedConflictError(
                    f"category stable code conflict in marketplace {marketplace_code}: {code}"
                )
            if by_slug is not None and by_slug.code != code:
                raise SeedConflictError(
                    f"category stable slug conflict in marketplace {marketplace_code}: {slug}"
                )
            if by_code is None:
                session.add(
                    Category(
                        marketplace_id=marketplace.id,
                        code=code,
                        slug=slug,
                        name=name,
                        sort_order=order,
                    )
                )

    location_by_code: dict[str, Location] = {}
    for definition in LOCATION_DEFINITIONS:
        parent = (
            location_by_code[definition.parent_code] if definition.parent_code is not None else None
        )
        matches = session.scalars(select(Location).where(Location.slug == definition.code)).all()
        if len(matches) > 1:
            raise SeedConflictError("location stable code is not globally unique")
        location = matches[0] if matches else None
        if location is not None and (
            location.parent_id != (parent.id if parent is not None else None)
            or location.country_code != definition.country_code
            or location.location_type != definition.location_type
        ):
            raise SeedConflictError(f"location stable code conflict: {definition.code}")
        if location is None:
            location = Location(
                parent_id=parent.id if parent is not None else None,
                country_code=definition.country_code,
                location_type=definition.location_type,
                name=definition.name,
                slug=definition.code,
            )
            session.add(location)
            session.flush()
        location_by_code[definition.code] = location

    for code, name in ROLES:
        role = session.scalar(select(Role).where(Role.code == code))
        if role is None:
            session.add(Role(code=code, name=name, is_system_role=True))

    session.flush()
    return SeedCounts(
        marketplaces=session.scalar(select(func.count()).select_from(Marketplace)) or 0,
        categories=session.scalar(select(func.count()).select_from(Category)) or 0,
        locations=session.scalar(select(func.count()).select_from(Location)) or 0,
        roles=session.scalar(select(func.count()).select_from(Role)) or 0,
    )


def main() -> None:
    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        raise SystemExit("DATABASE_URL is required")
    validate_development_url(raw_url)
    engine = create_database_engine(raw_url)
    with session_scope(engine) as session:
        counts = seed_canonical_taxonomy(session)
    print(
        f"Seed complete: marketplaces={counts.marketplaces}, "
        f"categories={counts.categories}, locations={counts.locations}, roles={counts.roles}"
    )


if __name__ == "__main__":
    main()
