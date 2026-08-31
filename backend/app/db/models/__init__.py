"""Import every model into the authoritative metadata."""

from app.db.models.catalogue import (
    Listing,
    ListingCategory,
    ListingContact,
    ListingLocation,
    ListingMedia,
    ListingSourcePayload,
    SourceTaxonomyMapping,
    Vendor,
)
from app.db.models.identity import Role, User, UserRole
from app.db.models.operations import AuditLog, SyncItemError, SyncRun, SystemAlert
from app.db.models.taxonomy import Category, Location, Marketplace

__all__ = [
    "AuditLog",
    "Category",
    "Listing",
    "ListingCategory",
    "ListingContact",
    "ListingLocation",
    "ListingMedia",
    "ListingSourcePayload",
    "Location",
    "Marketplace",
    "Role",
    "SourceTaxonomyMapping",
    "SyncItemError",
    "SyncRun",
    "SystemAlert",
    "User",
    "UserRole",
    "Vendor",
]
