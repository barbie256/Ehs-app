"""Central Gate 2 API router."""

from typing import TypedDict

from fastapi import APIRouter

from app import __version__


class RootResponse(TypedDict):
    """Controlled public startup response."""

    name: str
    version: str
    status: str


api_router = APIRouter()


@api_router.get("/", response_model=RootResponse)
def read_root() -> RootResponse:
    """Confirm that the configuration foundation can start."""
    return {
        "name": "EHS Mall API",
        "version": __version__,
        "status": "foundation-ready",
    }
