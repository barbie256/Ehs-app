"""Guarded test-only discovery checks, isolated by a rolled-back outer transaction."""

import asyncio
from collections.abc import Generator
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.db.models.catalogue import SourceTaxonomyMapping
from app.db.models.operations import SyncRun
from app.db.models.taxonomy import Category, Marketplace
from app.db.readiness import synchronization_readiness
from app.integrations.directorist.client import DirectoristClient
from app.repositories.catalogue import CatalogueRepository
from app.repositories.taxonomy import TaxonomyRepository
from app.services.catalogue_sync import CatalogueSyncService


@pytest.fixture
def discovery_session(test_database_engine: Engine) -> Generator[Session]:
    with test_database_engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        assert all(
            connection.execute(
                text(
                    "SELECT current_database()='ehs_mall_test', current_user='ehs_mall_local', "
                    "inet_server_addr() IN ('127.0.0.1'::inet, '::1'::inet)"
                )
            ).one()
        )
        connection.rollback()
    # The readiness helper only reads. Set its transactions read-only as well.
    from sqlalchemy import event

    def readonly(connection: object) -> None:
        from sqlalchemy import Connection

        assert isinstance(connection, Connection)
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")

    event.listen(test_database_engine, "begin", readonly)
    try:
        readiness = synchronization_readiness(test_database_engine)
        assert readiness.status == "current" and readiness.code_head == "0004_sync_and_audit"
    finally:
        event.remove(test_database_engine, "begin", readonly)
    with test_database_engine.connect() as connection:
        outer = connection.begin()
        try:
            with Session(
                bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
            ) as session:
                yield session
        finally:
            outer.rollback()


def test_rediscovery_preserves_decisions_and_targets(discovery_session: Session) -> None:
    session = discovery_session
    suffix = uuid4().hex
    marketplace = Marketplace(code="synthetic-" + suffix, name="Synthetic")
    session.add(marketplace)
    session.flush()
    category = Category(
        marketplace_id=marketplace.id, code="synthetic", slug="synthetic", name="Synthetic"
    )
    session.add(category)
    session.flush()
    identities = [str(uuid4().int) for _ in range(3)]
    approved, rejected, new = identities
    for identity, status in ((approved, "approved"), (rejected, "rejected")):
        session.add(
            SourceTaxonomyMapping(
                source_system="directorist",
                source_taxonomy="category",
                source_external_id=identity,
                source_name_snapshot="Old synthetic",
                mapping_status=status,
                marketplace_id=marketplace.id,
                category_id=category.id,
            )
        )
    session.flush()
    repository = TaxonomyRepository(session)
    records: list[tuple[str, str | None]] = [(identity, "New synthetic") for identity in identities]
    assert repository.discover("category", records).inserted == 1
    assert repository.discover("category", records).inserted == 0
    session.expire_all()
    rows = session.scalars(
        select(SourceTaxonomyMapping).where(
            SourceTaxonomyMapping.source_external_id.in_(identities)
        )
    ).all()
    assert len(rows) == 3
    for row in rows:
        if row.source_external_id == new:
            assert row.mapping_status == "pending"
            assert row.marketplace_id is row.category_id is row.location_id is None
        else:
            assert row.mapping_status == (
                "approved" if row.source_external_id == approved else "rejected"
            )
            assert (row.marketplace_id, row.category_id) == (marketplace.id, category.id)


@pytest.mark.parametrize("failure", [False, True])
def test_paged_discovery_and_failure_finalization(
    discovery_session: Session, failure: bool
) -> None:
    session = discovery_session
    identities = [uuid4().int for _ in range(3)]
    correlation = "phase7e-" + uuid4().hex
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.rsplit("/", 1)[-1]
        paths.append(path)
        if path == "categories":
            first = request.url.params["page"] == "1"
            if failure and not first:
                return httpx.Response(503, json={"private": "synthetic"})
            return httpx.Response(
                200,
                json=[
                    {"id": i, "name": "Synthetic"}
                    for i in (identities[:2] if first else identities[2:])
                ],
                headers={"X-WP-Total": "3", "X-WP-TotalPages": "2"},
            )
        return httpx.Response(200, json=[], headers={"X-WP-Total": "0", "X-WP-TotalPages": "0"})

    async def scenario() -> None:
        async with DirectoristClient(
            base_url="https://source.test", transport=httpx.MockTransport(handler), retry_count=0
        ) as source:
            result = await CatalogueSyncService(session, source, page_size=2).run(correlation)
            assert result.status == ("failed" if failure else "succeeded")
            assert result.exit_code == (12 if failure else 0)

    # Observe archival without touching unrelated synthetic test catalogue rows.
    with patch.object(CatalogueRepository, "archive_unseen", return_value=0) as archive:
        asyncio.run(scenario())
        assert archive.call_count == (0 if failure else 1)
    assert paths.count("categories") == 2
    assert paths.count("listings") == (0 if failure else 1)
    run = session.scalar(select(SyncRun).where(SyncRun.correlation_id == correlation))
    assert run is not None and run.completed_at is not None
    assert run.completed_at >= run.started_at
    assert run.status == ("failed" if failure else "succeeded")
    assert run.items_archived == 0
    count = session.scalar(
        select(func.count())
        .select_from(SourceTaxonomyMapping)
        .where(
            SourceTaxonomyMapping.source_external_id.in_([str(i) for i in identities]),
            SourceTaxonomyMapping.mapping_status == "pending",
            SourceTaxonomyMapping.marketplace_id.is_(None),
            SourceTaxonomyMapping.category_id.is_(None),
        )
    )
    assert count == (0 if failure else 3)
    assert (
        session.scalar(
            text(
                "SELECT count(*) FROM pg_locks WHERE locktype='advisory' "
                "AND classid::bigint=(499164875001::bigint >> 32) "
                "AND objid::bigint=(499164875001::bigint & 4294967295) AND objsubid=1 AND granted"
            )
        )
        == 0
    )
