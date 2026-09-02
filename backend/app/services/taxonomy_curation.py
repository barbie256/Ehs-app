"""Frozen human-approved Directorist taxonomy decisions and transactional curation."""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.catalogue import SourceTaxonomyMapping
from app.db.models.taxonomy import Category, Location, Marketplace

DecisionAction = Literal["approve", "reject"]
DecisionKind = Literal["directory", "category", "location"]


class TaxonomyCurationError(RuntimeError):
    """A controlled mismatch that prevents the complete decision set from applying."""


@dataclass(frozen=True)
class MappingDecision:
    source_system: Literal["directorist"]
    source_taxonomy: DecisionKind
    source_external_id: str
    expected_source_name: str
    action: DecisionAction
    marketplace_code: str | None = None
    target_code: str | None = None
    location_path: tuple[str, ...] = ()


INITIAL_MAPPING_DECISIONS = (
    MappingDecision("directorist", "category", "29", "Cement", "approve", "construction", "cement"),
    MappingDecision(
        "directorist", "category", "36", "Apartments", "approve", "property", "apartments"
    ),
    MappingDecision(
        "directorist",
        "category",
        "37",
        "Commercial Properties",
        "approve",
        "property",
        "commercial_properties",
    ),
    MappingDecision(
        "directorist", "category", "40", "Furniture", "approve", "home_interior", "furniture"
    ),
    MappingDecision(
        "directorist",
        "category",
        "46",
        "Architects",
        "approve",
        "professional_services",
        "architects",
    ),
    MappingDecision(
        "directorist",
        "category",
        "47",
        "Engineers",
        "approve",
        "professional_services",
        "engineers",
    ),
    MappingDecision(
        "directorist",
        "category",
        "62",
        "Energy Solutions",
        "approve",
        "construction",
        "energy_solutions",
    ),
    MappingDecision(
        "directorist", "category", "64", "Appliances", "approve", "home_interior", "appliances"
    ),
    MappingDecision(
        "directorist",
        "category",
        "65",
        "Building Materials",
        "approve",
        "construction",
        "building_materials",
    ),
    MappingDecision("directorist", "category", "66", "Doors", "approve", "construction", "doors"),
    MappingDecision(
        "directorist",
        "location",
        "51",
        "Kampala",
        "approve",
        target_code="kampala",
        location_path=("africa", "uganda", "kampala"),
    ),
    MappingDecision("directorist", "directory", "3", "Business", "reject"),
)


@dataclass(frozen=True)
class CurationCounts:
    total: int
    applied: int
    unchanged: int
    approved: int
    rejected: int


@dataclass(frozen=True)
class _ValidatedDecision:
    mapping: SourceTaxonomyMapping
    decision: MappingDecision
    marketplace: Marketplace | None = None
    category: Category | None = None
    location: Location | None = None


def apply_initial_taxonomy_mappings(session: Session) -> CurationCounts:
    """Validate the frozen inventory completely, then apply it as one unit of work."""
    identities = {
        (item.source_system, item.source_taxonomy, item.source_external_id)
        for item in INITIAL_MAPPING_DECISIONS
    }
    if len(identities) != len(INITIAL_MAPPING_DECISIONS):
        raise TaxonomyCurationError("mapping decision identities are not unique")

    validated = [_validate_decision(session, decision) for decision in INITIAL_MAPPING_DECISIONS]
    applied = 0
    approved = 0
    rejected = 0
    for item in validated:
        if _already_matches(item):
            continue
        mapping = item.mapping
        if item.decision.action == "reject":
            mapping.mapping_status = "rejected"
            mapping.marketplace_id = None
            mapping.category_id = None
            mapping.location_id = None
            mapping.mapping_reason = "human_approved_initial_baseline_rejection"
            rejected += 1
        else:
            mapping.mapping_status = "approved"
            mapping.marketplace_id = item.marketplace.id if item.marketplace is not None else None
            mapping.category_id = item.category.id if item.category is not None else None
            mapping.location_id = item.location.id if item.location is not None else None
            mapping.mapping_reason = "human_approved_initial_baseline"
            approved += 1
        applied += 1
    session.flush()
    return CurationCounts(
        total=len(validated),
        applied=applied,
        unchanged=len(validated) - applied,
        approved=approved,
        rejected=rejected,
    )


def _validate_decision(session: Session, decision: MappingDecision) -> _ValidatedDecision:
    mapping = session.scalar(
        select(SourceTaxonomyMapping).where(
            SourceTaxonomyMapping.source_system == decision.source_system,
            SourceTaxonomyMapping.source_taxonomy == decision.source_taxonomy,
            SourceTaxonomyMapping.source_external_id == decision.source_external_id,
        )
    )
    if mapping is None or mapping.source_name_snapshot != decision.expected_source_name:
        raise TaxonomyCurationError("source mapping identity or expected name mismatch")

    if decision.action == "reject":
        if decision.marketplace_code or decision.target_code or decision.location_path:
            raise TaxonomyCurationError("rejected decision must not contain a target")
        item = _ValidatedDecision(mapping, decision)
    elif decision.source_taxonomy == "category":
        item = _validate_category(session, mapping, decision)
    elif decision.source_taxonomy == "location":
        item = _validate_location(session, mapping, decision)
    else:
        raise TaxonomyCurationError("approved decision has unsupported taxonomy type")

    if mapping.mapping_status == "pending":
        if mapping.marketplace_id or mapping.category_id or mapping.location_id:
            raise TaxonomyCurationError("pending mapping already contains a target")
    elif not _already_matches(item):
        raise TaxonomyCurationError("existing mapping conflicts with approved decision")
    return item


def _validate_category(
    session: Session, mapping: SourceTaxonomyMapping, decision: MappingDecision
) -> _ValidatedDecision:
    if decision.marketplace_code is None or decision.target_code is None or decision.location_path:
        raise TaxonomyCurationError("category decision target is incomplete")
    marketplace = session.scalar(
        select(Marketplace).where(Marketplace.code == decision.marketplace_code)
    )
    if marketplace is None or not marketplace.is_active:
        raise TaxonomyCurationError("canonical marketplace is missing or inactive")
    category = session.scalar(
        select(Category).where(
            Category.marketplace_id == marketplace.id,
            Category.code == decision.target_code,
        )
    )
    if category is None or not category.is_active:
        raise TaxonomyCurationError("canonical category is missing or inactive")
    return _ValidatedDecision(mapping, decision, marketplace, category)


def _validate_location(
    session: Session, mapping: SourceTaxonomyMapping, decision: MappingDecision
) -> _ValidatedDecision:
    if (
        decision.marketplace_code is not None
        or decision.target_code is None
        or decision.location_path != ("africa", "uganda", "kampala")
        or decision.target_code != decision.location_path[-1]
    ):
        raise TaxonomyCurationError("location decision path is not the approved hierarchy")
    parent: Location | None = None
    for code in decision.location_path:
        matches = session.scalars(select(Location).where(Location.slug == code)).all()
        if len(matches) != 1:
            raise TaxonomyCurationError("canonical location is missing or ambiguous")
        location = matches[0]
        if not location.is_active or location.parent_id != (parent.id if parent else None):
            raise TaxonomyCurationError("canonical location hierarchy is invalid or inactive")
        parent = location
    if parent is None:
        raise TaxonomyCurationError("canonical location path is empty")
    return _ValidatedDecision(mapping, decision, location=parent)


def _already_matches(item: _ValidatedDecision) -> bool:
    mapping = item.mapping
    if item.decision.action == "reject":
        return (
            mapping.mapping_status == "rejected"
            and mapping.marketplace_id is None
            and mapping.category_id is None
            and mapping.location_id is None
        )
    if item.decision.source_taxonomy == "category":
        return (
            mapping.mapping_status == "approved"
            and item.marketplace is not None
            and item.category is not None
            and mapping.marketplace_id == item.marketplace.id
            and mapping.category_id == item.category.id
            and mapping.location_id is None
        )
    return (
        mapping.mapping_status == "approved"
        and item.location is not None
        and mapping.marketplace_id is None
        and mapping.category_id is None
        and mapping.location_id == item.location.id
    )
