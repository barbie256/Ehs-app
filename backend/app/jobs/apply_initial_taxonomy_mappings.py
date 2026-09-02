"""Apply the frozen human-approved initial taxonomy mapping baseline once."""

import logging
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import AppEnvironment, SettingsConfigurationError, get_settings
from app.db.readiness import synchronization_readiness
from app.db.session import (
    DatabaseSafetyError,
    create_database_engine,
    validate_development_url,
    validate_test_url,
)
from app.services.taxonomy_curation import (
    TaxonomyCurationError,
    apply_initial_taxonomy_mappings,
)

logger = logging.getLogger(__name__)

SUCCESS = 0
UNSAFE_CONFIGURATION = 10
DATABASE_NOT_READY = 11
DECISION_MISMATCH = 12
INTERNAL_FAILURE = 13


def run() -> int:
    """Validate boundaries and apply all committed decisions transactionally."""
    try:
        settings = get_settings()
        if settings.app_env is not AppEnvironment.DEVELOPMENT:
            raise SettingsConfigurationError("taxonomy curation requires development")
        database_url = settings.database_url.get_secret_value()
        validate_development_url(database_url)
        test_url = (
            settings.test_database_url.get_secret_value()
            if settings.test_database_url is not None
            else None
        )
        validate_test_url(test_url, development_url=database_url)
    except SettingsConfigurationError, DatabaseSafetyError:
        logger.error("taxonomy curation configuration rejected")
        return UNSAFE_CONFIGURATION

    engine = create_database_engine(database_url)
    try:
        readiness = synchronization_readiness(
            engine, backend_dir=Path(__file__).resolve().parents[2]
        )
        if readiness.status != "current":
            logger.error("taxonomy curation database readiness rejected")
            return DATABASE_NOT_READY
        with Session(engine) as session:
            try:
                counts = apply_initial_taxonomy_mappings(session)
                session.commit()
            except TaxonomyCurationError:
                session.rollback()
                logger.error("taxonomy curation decision set rejected")
                return DECISION_MISMATCH
        logger.info(
            "taxonomy curation completed total=%d applied=%d unchanged=%d approved=%d rejected=%d",
            counts.total,
            counts.applied,
            counts.unchanged,
            counts.approved,
            counts.rejected,
        )
        return SUCCESS
    except SQLAlchemyError:
        logger.error("taxonomy curation database failure")
        return DATABASE_NOT_READY
    except Exception:
        logger.error("taxonomy curation failed safely")
        return INTERNAL_FAILURE
    finally:
        engine.dispose()


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
