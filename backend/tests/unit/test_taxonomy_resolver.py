"""Database resolver behavior without network access."""

from typing import cast
from uuid import UUID

from app.repositories.taxonomy import ApprovedCategory, TaxonomyRepository
from app.services.taxonomy_resolver import DatabaseTaxonomyResolver


class ResolverRepository:
    def approved_categories(self) -> dict[int, ApprovedCategory]:
        return {
            29: ApprovedCategory(
                UUID("00000000-0000-0000-0000-000000000001"),
                "construction",
                "Construction",
                UUID("00000000-0000-0000-0000-000000000002"),
                "cement",
                "Cement",
            )
        }

    def approved_locations(self) -> dict[int, UUID]:
        return {51: UUID("00000000-0000-0000-0000-000000000003")}


def test_resolver_returns_only_explicit_approved_identities() -> None:
    repository = cast(TaxonomyRepository, ResolverRepository())
    resolver = DatabaseTaxonomyResolver(repository)

    assert resolver.resolve_category(29) is not None
    assert resolver.resolve_category(999) is None
    assert resolver.location_id(51) == UUID("00000000-0000-0000-0000-000000000003")
    assert resolver.location_id(999) is None
