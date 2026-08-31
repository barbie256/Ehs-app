"""Guarded migration rehearsal, database inventory, constraints, and seeds."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401
from alembic import command
from app.db.base import Base
from app.db.models.catalogue import Listing, Vendor
from app.db.models.identity import Role, User
from app.db.models.taxonomy import Category, Location
from app.db.readiness import migration_head_status
from app.services.taxonomy_seed import SeedConflictError, seed_canonical_taxonomy
from tests.conftest import BACKEND_DIR, private_urls


def alembic_config() -> Config:
    _, test_url = private_urls()
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", test_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def test_01_upgrade_downgrade_upgrade_rehearsal(test_database_engine: Engine) -> None:
    config = alembic_config()
    command.downgrade(config, "base")
    assert set(inspect(test_database_engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(config, "head")
    with Session(test_database_engine) as session:
        first = seed_canonical_taxonomy(session)
        session.commit()
        second = seed_canonical_taxonomy(session)
        session.commit()
        assert first == second
        assert (second.marketplaces, second.categories, second.roles) == (4, 44, 5)
        assert session.scalar(select(func.count()).select_from(User)) == 0
        assert session.scalar(select(func.count()).select_from(Vendor)) == 0
        assert session.scalar(select(func.count()).select_from(Listing)) == 0
    command.downgrade(config, "base")
    assert set(inspect(test_database_engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(config, "head")
    status = migration_head_status(test_database_engine, backend_dir=BACKEND_DIR)
    assert status.status == "current"
    assert status.current_revision == "0004_sync_and_audit"


def test_01b_rewritten_schema_matches_current_orm_metadata(
    test_database_engine: Engine,
) -> None:
    with test_database_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_02_final_database_inventory(test_database_engine: Engine) -> None:
    inspector = inspect(test_database_engine)
    expected = {
        "alembic_version",
        "users",
        "roles",
        "user_roles",
        "marketplaces",
        "categories",
        "locations",
        "vendors",
        "source_taxonomy_mappings",
        "listings",
        "listing_categories",
        "listing_locations",
        "listing_media",
        "listing_contacts",
        "listing_source_payloads",
        "sync_runs",
        "sync_item_errors",
        "audit_logs",
        "system_alerts",
    }
    assert set(inspector.get_table_names()) == expected


def test_03_seed_is_idempotent_and_non_creating(test_database_engine: Engine) -> None:
    with Session(test_database_engine) as session:
        first = seed_canonical_taxonomy(session)
        session.commit()
        second = seed_canonical_taxonomy(session)
        session.commit()
        assert first == second
        assert (second.marketplaces, second.categories, second.roles) == (4, 44, 5)
        assert session.scalar(select(func.count()).select_from(User)) == 0
        assert session.scalar(select(func.count()).select_from(Vendor)) == 0
        assert session.scalar(select(func.count()).select_from(Listing)) == 0


def test_04_duplicate_names_are_marketplace_scoped(test_database_engine: Engine) -> None:
    with Session(test_database_engine) as session:
        tiles = session.scalars(select(Category).where(Category.name == "Tiles")).all()
        sanitary = session.scalars(select(Category).where(Category.name == "Sanitary Ware")).all()
        assert len(tiles) == 2
        assert len(sanitary) == 2
        assert len({item.marketplace_id for item in tiles}) == 2


def test_05_seed_preserves_edited_display_name(test_database_engine: Engine) -> None:
    with Session(test_database_engine) as session:
        role = session.scalar(select(Role).where(Role.code == "customer"))
        assert role is not None
        original = role.name
        role.name = "Customer edited by administrator"
        session.commit()
        seed_canonical_taxonomy(session)
        session.commit()
        assert role.name == "Customer edited by administrator"
        role.name = original
        session.commit()


def test_06_stable_identity_conflict_fails(test_database_engine: Engine) -> None:
    with Session(test_database_engine) as session:
        category = session.scalar(select(Category).where(Category.code == "cement"))
        assert category is not None
        original = category.slug
        category.slug = "cement-administrator-conflict"
        session.commit()
        with pytest.raises(SeedConflictError):
            seed_canonical_taxonomy(session)
        session.rollback()
        category.slug = original
        session.commit()


def test_07_pending_marketplace_rule_is_enforced(test_database_engine: Engine) -> None:
    with Session(test_database_engine) as session:
        session.add(
            Listing(
                source_system="test",
                external_id="invalid-marketplace",
                title="x",
                source_status="publish",
                status="active",
                classification_status="mapped",
                pricing_type="fixed",
                source_url="https://example.invalid",
                source_checksum="0" * 64,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_08_self_parent_and_coordinate_rules_are_enforced(test_database_engine: Engine) -> None:
    with Session(test_database_engine) as session:
        location = Location(
            id="00000000-0000-0000-0000-000000000001",
            parent_id="00000000-0000-0000-0000-000000000001",
            country_code="UG",
            location_type="city",
            name="Invalid",
            slug="invalid",
            latitude=91,
            longitude=181,
        )
        session.add(location)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_09_application_import_does_not_mutate_schema(test_database_engine: Engine) -> None:
    before = set(inspect(test_database_engine).get_table_names())
    from app.main import create_app

    create_app()
    after = set(inspect(test_database_engine).get_table_names())
    assert after == before
