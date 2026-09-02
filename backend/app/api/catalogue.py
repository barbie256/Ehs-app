"""Thin synchronous public catalogue routes."""

from collections.abc import Generator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.readiness import synchronization_readiness
from app.db.session import create_database_engine
from app.repositories.public_catalogue import ListingFilters, PublicCatalogueRepository
from app.schemas.public_catalogue import (
    CategoryResponse,
    ListingDetailResponse,
    ListingOrderBy,
    ListingPageResponse,
    LocationResponse,
    MarketplaceResponse,
    SortOrder,
)
from app.services.public_catalogue import (
    PublicCatalogueService,
    PublicListingNotFound,
    normalize_search,
)

router = APIRouter(prefix="/api/v1", tags=["catalogue"])
UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Catalogue temporarily unavailable"
)


def catalogue_session() -> Generator[Session]:
    """Open one read-only request session after a fail-closed readiness check."""
    engine = create_database_engine(get_settings().database_url.get_secret_value())
    session: Session | None = None
    try:
        try:
            ready = synchronization_readiness(engine)
        except Exception:
            raise UNAVAILABLE from None
        if ready.status != "current":
            raise UNAVAILABLE
        session = sessionmaker(bind=engine, expire_on_commit=False)()
        session.execute(text("SET TRANSACTION READ ONLY"))
        yield session
        session.rollback()
    except HTTPException:
        raise
    except SQLAlchemyError:
        raise UNAVAILABLE from None
    finally:
        if session is not None:
            session.rollback()
            session.close()
        engine.dispose()


def service(session: Annotated[Session, Depends(catalogue_session)]) -> PublicCatalogueService:
    return PublicCatalogueService(PublicCatalogueRepository(session))


@router.get("/marketplaces", response_model=list[MarketplaceResponse])
def marketplaces(
    api: Annotated[PublicCatalogueService, Depends(service)],
) -> list[MarketplaceResponse]:
    return api.marketplaces()


@router.get("/categories", response_model=list[CategoryResponse])
def categories(
    api: Annotated[PublicCatalogueService, Depends(service)],
    marketplace: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
) -> list[CategoryResponse]:
    return api.categories(marketplace)


@router.get("/locations", response_model=list[LocationResponse])
def locations(api: Annotated[PublicCatalogueService, Depends(service)]) -> list[LocationResponse]:
    return api.locations()


@router.get("/listings", response_model=ListingPageResponse)
def listings(
    api: Annotated[PublicCatalogueService, Depends(service)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=50)] = 20,
    marketplace: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
    category: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    location: Annotated[str | None, Query(min_length=1, max_length=150)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    featured: bool | None = None,
    order_by: ListingOrderBy = ListingOrderBy.NEWEST,
    order: SortOrder = SortOrder.DESC,
) -> ListingPageResponse:
    try:
        search = normalize_search(q)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    location_ids = api.repository.location_descendants(location) if location is not None else None
    return api.listings(
        ListingFilters(
            page=page,
            per_page=per_page,
            marketplace=marketplace,
            category=category,
            location_ids=location_ids,
            search=search,
            featured=featured,
            order_by=order_by,
            order=order,
        )
    )


@router.get("/listings/{listing_id}", response_model=ListingDetailResponse)
def listing(
    listing_id: UUID, api: Annotated[PublicCatalogueService, Depends(service)]
) -> ListingDetailResponse:
    try:
        return api.listing(listing_id)
    except PublicListingNotFound:
        raise HTTPException(status_code=404, detail="Listing not found") from None
