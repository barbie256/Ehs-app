"""FastAPI application foundation."""

from fastapi import FastAPI

from app import __version__
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    """Build the Gate 2 application without database or external API access."""
    settings = get_settings()
    configure_logging(settings.log_level)

    application = FastAPI(title="EHS Mall API", version=__version__)
    application.include_router(api_router)
    return application


app = create_app()
