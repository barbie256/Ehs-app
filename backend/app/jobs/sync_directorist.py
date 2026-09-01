"""Run one Directorist catalogue synchronization with documented exit codes."""

import asyncio
import logging
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import SettingsConfigurationError, get_settings
from app.db.readiness import migration_head_status
from app.db.session import DatabaseSafetyError, create_database_engine, validate_development_url
from app.integrations.directorist.client import DirectoristClient
from app.services.catalogue_sync import CatalogueSyncService

logger = logging.getLogger(__name__)


async def _run() -> int:
    try:
        settings = get_settings()
        database_url = settings.database_url.get_secret_value()
        validate_development_url(database_url)
    except SettingsConfigurationError, DatabaseSafetyError:
        logger.error("catalogue sync configuration rejected")
        return 10

    engine = create_database_engine(database_url)
    try:
        readiness = migration_head_status(engine, backend_dir=Path(__file__).resolve().parents[2])
        if readiness.status != "current":
            logger.error("catalogue sync requires the database at the current migration head")
            return 11
        with (
            engine.connect() as connection,
            Session(bind=connection, expire_on_commit=False) as session,
        ):
            async with DirectoristClient(
                base_url=settings.directorist_base_url,
                timeout_seconds=settings.directorist_request_timeout_seconds,
                max_pages=settings.directorist_max_pages,
                max_page_size=settings.directorist_page_size,
            ) as source:
                result = await CatalogueSyncService(
                    session, source, page_size=settings.directorist_page_size
                ).run()
                logger.info(
                    "catalogue sync completed status=%s received=%d failed=%d",
                    result.status,
                    result.counts.items_received,
                    result.counts.items_failed,
                )
                return result.exit_code
    except SQLAlchemyError:
        logger.error("catalogue sync database connection failed")
        return 11
    except Exception:
        logger.error("catalogue sync process failed safely")
        return 13
    finally:
        engine.dispose()


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
