"""Offline-testable Directorist catalogue synchronization orchestration."""

from dataclasses import dataclass, field
from html import unescape
from typing import Any, Literal, Protocol
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.integrations.directorist.errors import DirectoristError, DirectoristMappingError
from app.integrations.directorist.mapper import map_listing, plain_text
from app.integrations.directorist.schemas import DirectoristValidatedPage
from app.repositories.catalogue import CatalogueRepository
from app.repositories.sync import SyncRepository
from app.repositories.taxonomy import DiscoveryCounts, TaxonomyRepository
from app.services.taxonomy_resolver import DatabaseTaxonomyResolver


class SyncSource(Protocol):
    async def get_directories(self) -> list[dict[str, Any]]: ...

    async def get_categories(self) -> list[dict[str, Any]]: ...

    async def get_locations(self) -> list[dict[str, Any]]: ...

    async def get_validated_listings_page(
        self, page: int, per_page: int
    ) -> DirectoristValidatedPage: ...


@dataclass
class SyncCounts:
    pages_requested: int = 0
    items_received: int = 0
    items_inserted: int = 0
    items_updated: int = 0
    items_unchanged: int = 0
    items_archived: int = 0
    items_pending_mapping: int = 0
    items_failed: int = 0

    def database_values(self) -> dict[str, int]:
        return vars(self).copy()


@dataclass(frozen=True)
class SyncResult:
    status: str
    exit_code: int
    counts: SyncCounts
    taxonomy: dict[str, DiscoveryCounts] = field(default_factory=dict)
    error_code: str | None = None


class CatalogueSyncService:
    def __init__(self, session: Session, source: SyncSource, *, page_size: int = 20) -> None:
        self.session = session
        self.source = source
        self.page_size = page_size
        self.sync_repository = SyncRepository(session)
        self.taxonomy_repository = TaxonomyRepository(session)
        self.catalogue_repository = CatalogueRepository(session)

    async def run(self, correlation_id: str | None = None) -> SyncResult:
        counts = SyncCounts()
        taxonomy_counts: dict[str, DiscoveryCounts] = {}
        run = self.sync_repository.start(correlation_id or str(uuid4()))
        self.session.commit()
        locked = False
        result: SyncResult | None = None
        try:
            locked = self.sync_repository.try_lock()
            self.session.commit()
            if not locked:
                self.sync_repository.finish(run, "skipped", **counts.database_values())
                self.session.commit()
                return SyncResult("skipped", 2, counts)

            taxonomy_counts = await self._sync_taxonomies()
            self.session.commit()
            resolver = DatabaseTaxonomyResolver(self.taxonomy_repository)
            page_number = 1
            while True:
                counts.pages_requested += 1
                page = await self.source.get_validated_listings_page(page_number, self.page_size)
                if page.current_page != page_number:
                    raise DirectoristError("pagination sequence is incomplete")
                counts.items_received += len(page.items) + len(page.failures)
                for failure in page.failures:
                    counts.items_failed += 1
                    self.sync_repository.item_error(
                        run.id,
                        failure.external_id,
                        failure.error_code,
                        failure.field_summary,
                    )
                for source_listing in page.items:
                    try:
                        with self.session.begin_nested():
                            normalized = map_listing(source_listing, resolver)
                            outcome = self.catalogue_repository.upsert(normalized, resolver)
                            setattr(
                                counts,
                                f"items_{outcome.outcome}",
                                getattr(counts, f"items_{outcome.outcome}") + 1,
                            )
                            if outcome.pending_mapping:
                                counts.items_pending_mapping += 1
                    except DirectoristMappingError, ValueError:
                        counts.items_failed += 1
                        self.sync_repository.item_error(
                            run.id,
                            str(source_listing.id),
                            "classification_conflict",
                            "categories",
                        )
                self.session.commit()
                if page.next_page is None:
                    break
                if page.next_page != page_number + 1:
                    raise DirectoristError("pagination sequence is incomplete")
                page_number = page.next_page

            if counts.items_failed:
                status, exit_code = "partial", 3
            else:
                counts.items_archived = self.catalogue_repository.archive_unseen(run.started_at)
                status, exit_code = "succeeded", 0
            self.sync_repository.finish(run, status, **counts.database_values())
            self.session.commit()
            result = SyncResult(status, exit_code, counts, taxonomy_counts)
        except DirectoristError as error:
            self.session.rollback()
            run = self.session.get(type(run), run.id) or run
            self.sync_repository.fail(
                run,
                "directorist_" + error.code,
                "Directorist synchronization failed",
                **counts.database_values(),
            )
            self.session.commit()
            result = SyncResult("failed", 12, counts, taxonomy_counts, error.code)
        except SQLAlchemyError:
            self.session.rollback()
            run = self.session.get(type(run), run.id) or run
            self.sync_repository.fail(
                run, "database_error", "Database synchronization failed", **counts.database_values()
            )
            self.session.commit()
            result = SyncResult("failed", 11, counts, taxonomy_counts, "database_error")
        except Exception:
            self.session.rollback()
            run = self.session.get(type(run), run.id) or run
            self.sync_repository.fail(
                run,
                "controlled_failure",
                "Synchronization failed safely",
                **counts.database_values(),
            )
            self.session.commit()
            result = SyncResult("failed", 13, counts, taxonomy_counts, "controlled_failure")
        finally:
            if locked:
                try:
                    released = self.sync_repository.unlock()
                    self.session.commit()
                except SQLAlchemyError:
                    self.session.rollback()
                    released = False
                if (
                    not released
                    and result is not None
                    and result.status in {"succeeded", "partial"}
                ):
                    result = SyncResult(
                        "failed", 11, counts, taxonomy_counts, "lock_release_failed"
                    )
        if result is None:
            return SyncResult("failed", 13, counts, taxonomy_counts, "controlled_failure")
        return result

    async def _sync_taxonomies(self) -> dict[str, DiscoveryCounts]:
        collections: list[
            tuple[Literal["directory", "category", "location"], list[dict[str, Any]]]
        ] = [
            ("directory", await self.source.get_directories()),
            ("category", await self.source.get_categories()),
            ("location", await self.source.get_locations()),
        ]
        return {
            kind: self.taxonomy_repository.discover(kind, self._safe_taxonomy_records(records))
            for kind, records in collections
        }

    @staticmethod
    def _safe_taxonomy_records(records: list[dict[str, Any]]) -> list[tuple[str, str | None]]:
        safe: dict[str, str | None] = {}
        for record in records:
            external_id = record.get("id")
            if not isinstance(external_id, int) or external_id < 1:
                raise DirectoristError("taxonomy collection contains an invalid identity")
            name = record.get("name")
            snapshot = plain_text(name if isinstance(name, str) else None, limit=200)
            safe[str(external_id)] = unescape(snapshot) or None
        return sorted(safe.items(), key=lambda item: int(item[0]))
