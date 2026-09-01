"""Database-backed, name-agnostic Directorist taxonomy resolution."""

from uuid import UUID

from app.repositories.taxonomy import ApprovedCategory, TaxonomyRepository
from app.schemas.catalogue import CanonicalMapping


class DatabaseTaxonomyResolver:
    def __init__(self, repository: TaxonomyRepository) -> None:
        self._categories: dict[int, ApprovedCategory] = repository.approved_categories()
        self._locations = repository.approved_locations()

    def resolve_category(self, external_id: int) -> CanonicalMapping | None:
        resolved = self._categories.get(external_id)
        if resolved is None:
            return None
        return CanonicalMapping(
            marketplace_code=resolved.marketplace_code,
            marketplace_name=resolved.marketplace_name,
            category_code=resolved.category_code,
            category_name=resolved.category_name,
        )

    def category(self, external_id: int) -> ApprovedCategory | None:
        return self._categories.get(external_id)

    def location_id(self, external_id: int) -> UUID | None:
        return self._locations.get(external_id)
