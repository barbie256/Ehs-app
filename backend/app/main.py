"""FastAPI application foundation."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import AppEnvironment, get_settings
from app.core.logging import configure_logging

DEVELOPMENT_WEB_ORIGINS = (
    "http://localhost:8081",
    "http://127.0.0.1:8081",
)


def create_app() -> FastAPI:
    """Build the Gate 2 application without database or external API access."""
    settings = get_settings()
    configure_logging(settings.log_level)

    application = FastAPI(title="EHS Mall API", version=__version__)
    if settings.app_env is AppEnvironment.DEVELOPMENT:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(DEVELOPMENT_WEB_ORIGINS),
            allow_credentials=False,
            allow_methods=["GET", "OPTIONS"],
            allow_headers=["Accept"],
        )
    application.include_router(api_router)
    return application


app = create_app()
