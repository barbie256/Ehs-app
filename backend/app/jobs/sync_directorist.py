"""Run one Directorist catalogue synchronization with documented exit codes."""

import asyncio
import logging
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, Settings, SettingsConfigurationError, get_settings
from app.db.readiness import synchronization_readiness
from app.db.session import DatabaseSafetyError, create_database_engine, validate_development_url
from app.integrations.directorist.client import DirectoristClient
from app.services.catalogue_sync import CatalogueSyncService

logger = logging.getLogger(__name__)


def _validate_job_boundary(settings: Settings) -> None:
    """Require the single approved environment and source before any I/O."""
    if settings.app_env is not AppEnvironment.DEVELOPMENT:
        raise SettingsConfigurationError("catalogue synchronization requires development")
    try:
        source = urlsplit(settings.directorist_base_url)
        port = source.port
    except ValueError:
        raise SettingsConfigurationError("catalogue synchronization source is invalid") from None
    if (
        source.scheme != "https"
        or source.hostname != "ehsmall.com"
        or port not in {None, 443}
        or source.username is not None
        or source.password is not None
        or source.path not in {"", "/"}
        or source.query
        or source.fragment
        or settings.directorist_api_version != "v1"
    ):
        raise SettingsConfigurationError("catalogue synchronization source is not approved")


async def _run() -> int:
    try:
        settings = get_settings()
        _validate_job_boundary(settings)
        database_url = settings.database_url.get_secret_value()
        validate_development_url(database_url)
    except SettingsConfigurationError, DatabaseSafetyError:
        logger.error("catalogue sync configuration rejected")
        return 10

    engine = create_database_engine(database_url)
    try:
        readiness = synchronization_readiness(
            engine, backend_dir=Path(__file__).resolve().parents[2]
        )
        if readiness.status != "current":
            logger.error("catalogue sync database readiness rejected")
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
