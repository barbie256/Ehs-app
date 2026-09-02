"""Guarded transactional tests for canonical taxonomy and initial curation."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.db.models.catalogue import (
    Listing,
    ListingContact,
    ListingMedia,
    ListingSourcePayload,
    SourceTaxonomyMapping,
)
from app.db.models.identity import Role, UserRole
from app.db.models.taxonomy import Category, Location, Marketplace
from app.services.taxonomy_curation import (
    INITIAL_MAPPING_DECISIONS,
    TaxonomyCurationError,
    apply_initial_taxonomy_mappings,
)
from app.services.taxonomy_seed import SeedConflictError, seed_canonical_taxonomy


@contextmanager
def rollback_session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def clear_canonical_state(session: Session) -> None:
    session.execute(delete(UserRole))
    session.execute(delete(Listing))
    session.execute(delete(SourceTaxonomyMapping))
    session.execute(delete(Category))
    session.execute(delete(Location))
    session.execute(delete(Marketplace))
    session.execute(delete(Role))
    session.flush()


def add_pending_decisions(session: Session) -> None:
    session.add_all(
        [
            SourceTaxonomyMapping(
                source_system=item.source_system,
                source_taxonomy=item.source_taxonomy,
                source_external_id=item.source_external_id,
                source_name_snapshot=item.expected_source_name,
                mapping_status="pending",
            )
            for item in INITIAL_MAPPING_DECISIONS
        ]
    )
    session.flush()


def test_seed_expansion_is_idempotent_and_preserves_display_names(
    test_database_engine: Engine,
) -> None:
    with rollback_session(test_database_engine) as session:
        clear_canonical_state(session)
        first = seed_canonical_taxonomy(session)
        assert (first.marketplaces, first.categories, first.locations, first.roles) == (4, 46, 3, 5)
        africa = session.scalar(select(Location).where(Location.slug == "africa"))
        uganda = session.scalar(select(Location).where(Location.slug == "uganda"))
        kampala = session.scalar(select(Location).where(Location.slug == "kampala"))
        assert africa is not None and africa.parent_id is None
        assert uganda is not None and uganda.parent_id == africa.id
        assert kampala is not None and kampala.parent_id == uganda.id
        kampala.name = "Administrator-edited Kampala"
        second = seed_canonical_taxonomy(session)
        assert second == first
        assert kampala.name == "Administrator-edited Kampala"


def test_location_stable_identity_conflict_fails(test_database_engine: Engine) -> None:
    with rollback_session(test_database_engine) as session:
        clear_canonical_state(session)
        seed_canonical_taxonomy(session)
        kampala = session.scalar(select(Location).where(Location.slug == "kampala"))
        africa = session.scalar(select(Location).where(Location.slug == "africa"))
        assert kampala is not None and africa is not None
        kampala.parent_id = africa.id
        session.flush()
        with pytest.raises(SeedConflictError, match="location stable code conflict"):
            seed_canonical_taxonomy(session)


def test_all_decisions_apply_atomically_and_second_run_is_idempotent(
    test_database_engine: Engine,
) -> None:
    with rollback_session(test_database_engine) as session:
        clear_canonical_state(session)
        seed_canonical_taxonomy(session)
        add_pending_decisions(session)
        protected_before = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Listing, ListingSourcePayload, ListingMedia, ListingContact)
        )

        first = apply_initial_taxonomy_mappings(session)
        assert (first.total, first.applied, first.unchanged, first.approved, first.rejected) == (
            12,
            12,
            0,
            11,
            1,
        )
        mappings = session.scalars(select(SourceTaxonomyMapping)).all()
        business = next(item for item in mappings if item.source_taxonomy == "directory")
        assert business.mapping_status == "rejected"
        assert business.marketplace_id is business.category_id is business.location_id is None
        kampala_mapping = next(item for item in mappings if item.source_taxonomy == "location")
        kampala = session.scalar(select(Location).where(Location.slug == "kampala"))
        assert kampala is not None and kampala_mapping.location_id == kampala.id
        for mapping in (item for item in mappings if item.source_taxonomy == "category"):
            assert mapping.mapping_status == "approved"
            assert mapping.marketplace_id is not None and mapping.category_id is not None
            category = session.get(Category, mapping.category_id)
            assert category is not None and category.marketplace_id == mapping.marketplace_id

        second = apply_initial_taxonomy_mappings(session)
        assert (second.applied, second.unchanged) == (0, 12)
        protected_after = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Listing, ListingSourcePayload, ListingMedia, ListingContact)
        )
        assert protected_after == protected_before


@pytest.mark.parametrize("failure", ["missing", "name", "inactive"])
def test_validation_failure_has_no_partial_mapping_changes(
    test_database_engine: Engine, failure: str
) -> None:
    with rollback_session(test_database_engine) as session:
        clear_canonical_state(session)
        seed_canonical_taxonomy(session)
        add_pending_decisions(session)
        if failure == "missing":
            session.execute(
                delete(SourceTaxonomyMapping).where(
                    SourceTaxonomyMapping.source_taxonomy == "category",
                    SourceTaxonomyMapping.source_external_id == "66",
                )
            )
        elif failure == "name":
            mapping = session.scalar(
                select(SourceTaxonomyMapping).where(
                    SourceTaxonomyMapping.source_taxonomy == "category",
                    SourceTaxonomyMapping.source_external_id == "66",
                )
            )
            assert mapping is not None
            mapping.source_name_snapshot = "Unexpected public name"
        else:
            category = session.scalar(select(Category).where(Category.code == "building_materials"))
            assert category is not None
            category.is_active = False
        session.flush()

        with pytest.raises(TaxonomyCurationError):
            apply_initial_taxonomy_mappings(session)
        statuses = set(session.scalars(select(SourceTaxonomyMapping.mapping_status)))
        assert statuses == {"pending"}


def test_conflicting_existing_target_fails_closed(test_database_engine: Engine) -> None:
    with rollback_session(test_database_engine) as session:
        clear_canonical_state(session)
        seed_canonical_taxonomy(session)
        add_pending_decisions(session)
        mapping = session.scalar(
            select(SourceTaxonomyMapping).where(
                SourceTaxonomyMapping.source_taxonomy == "category",
                SourceTaxonomyMapping.source_external_id == "29",
            )
        )
        wrong_marketplace = session.scalar(
            select(Marketplace).where(Marketplace.code == "property")
        )
        assert mapping is not None and wrong_marketplace is not None
        wrong_category = session.scalar(
            select(Category).where(
                Category.marketplace_id == wrong_marketplace.id,
                Category.code == "apartments",
            )
        )
        assert wrong_category is not None
        mapping.mapping_status = "approved"
        mapping.marketplace_id = wrong_marketplace.id
        mapping.category_id = wrong_category.id
        session.flush()
        with pytest.raises(TaxonomyCurationError, match="conflicts"):
            apply_initial_taxonomy_mappings(session)
