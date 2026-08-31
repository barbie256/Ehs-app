"""Logging configuration that accepts only a validated level."""

import logging
from logging.config import dictConfig


def configure_logging(level: str) -> None:
    """Configure concise application logs without serializing settings."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": level,
                }
            },
            "root": {"handlers": ["default"], "level": level},
        }
    )
    logging.getLogger(__name__).info("logging_configured")
