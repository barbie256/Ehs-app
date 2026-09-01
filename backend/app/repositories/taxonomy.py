"""Persistence operations for source and canonical taxonomy."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models.catalogue import SourceTaxonomyMapping
from app.db.models.taxonomy import Category, Location, Marketplace

TaxonomyKind = Literal["directory", "category", "location"]


@dataclass(frozen=True)
class DiscoveryCounts:
    inserted: int = 0
    unchanged: int = 0
    changed: int = 0


@dataclass(frozen=True)
class ApprovedCategory:
    marketplace_id: UUID
    marketplace_code: str
    marketplace_name: str
    category_id: UUID
    category_code: str
    category_name: str


class TaxonomyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def discover(
        self, kind: TaxonomyKind, records: list[tuple[str, str | None]]
    ) -> DiscoveryCounts:
        counts = [0, 0, 0]
        for external_id, name in records:
            existing = self.session.scalar(
                select(SourceTaxonomyMapping).where(
                    SourceTaxonomyMapping.source_system == "directorist",
                    SourceTaxonomyMapping.source_taxonomy == kind,
                    SourceTaxonomyMapping.source_external_id == external_id,
                )
            )
            if existing is None:
                self.session.execute(
                    insert(SourceTaxonomyMapping).values(
                        source_system="directorist",
                        source_taxonomy=kind,
                        source_external_id=external_id,
                        source_name_snapshot=name,
                        mapping_status="pending",
                    )
                )
                counts[0] += 1
            elif existing.source_name_snapshot != name:
                existing.source_name_snapshot = name
                existing.updated_at = datetime.now(UTC)
                counts[2] += 1
            else:
                counts[1] += 1
        self.session.flush()
        return DiscoveryCounts(*counts)

    def approved_categories(self) -> dict[int, ApprovedCategory]:
        rows = self.session.execute(
            select(SourceTaxonomyMapping, Category, Marketplace)
            .join(Category, SourceTaxonomyMapping.category_id == Category.id)
            .join(Marketplace, Category.marketplace_id == Marketplace.id)
            .where(
                SourceTaxonomyMapping.source_system == "directorist",
                SourceTaxonomyMapping.source_taxonomy == "category",
                SourceTaxonomyMapping.mapping_status == "approved",
                SourceTaxonomyMapping.marketplace_id == Marketplace.id,
            )
        ).all()
        result: dict[int, ApprovedCategory] = {}
        for mapping, category, marketplace in rows:
            try:
                external_id = int(mapping.source_external_id)
            except ValueError:
                continue
            result[external_id] = ApprovedCategory(
                marketplace.id,
                marketplace.code,
                marketplace.name,
                category.id,
                category.code,
                category.name,
            )
        return result

    def approved_locations(self) -> dict[int, UUID]:
        rows = self.session.execute(
            select(SourceTaxonomyMapping.source_external_id, Location.id)
            .join(Location, SourceTaxonomyMapping.location_id == Location.id)
            .where(
                SourceTaxonomyMapping.source_system == "directorist",
                SourceTaxonomyMapping.source_taxonomy == "location",
                SourceTaxonomyMapping.mapping_status == "approved",
            )
        )
        result: dict[int, UUID] = {}
        for source_external_id, location_id in rows:
            try:
                result[int(source_external_id)] = location_id
            except ValueError:
                continue
        return result
