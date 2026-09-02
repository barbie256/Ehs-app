"""Frozen initial taxonomy decisions and Africa-ready seed definitions."""

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.schemas.catalogue import NormalizedListing
from app.services.taxonomy_curation import INITIAL_MAPPING_DECISIONS
from app.services.taxonomy_seed import (
    CATEGORY_NAMES,
    LOCATION_DEFINITIONS,
    LocationSeed,
    SeedConflictError,
    validate_location_definitions,
)


def test_decision_inventory_is_exact_unique_and_immutable() -> None:
    identities = {
        (item.source_system, item.source_taxonomy, item.source_external_id)
        for item in INITIAL_MAPPING_DECISIONS
    }
    assert len(INITIAL_MAPPING_DECISIONS) == len(identities) == 12
    assert (
        sum(
            item.source_taxonomy == "category" and item.action == "approve"
            for item in INITIAL_MAPPING_DECISIONS
        )
        == 10
    )
    assert (
        sum(
            item.source_taxonomy == "location" and item.action == "approve"
            for item in INITIAL_MAPPING_DECISIONS
        )
        == 1
    )
    assert (
        sum(
            item.source_taxonomy == "directory" and item.action == "reject"
            for item in INITIAL_MAPPING_DECISIONS
        )
        == 1
    )
    with pytest.raises(FrozenInstanceError):
        INITIAL_MAPPING_DECISIONS[0].action = "reject"  # type: ignore[misc]


def test_approved_decisions_are_frozen_exactly() -> None:
    actual = {
        (
            item.source_taxonomy,
            item.source_external_id,
            item.expected_source_name,
            item.action,
            item.marketplace_code,
            item.target_code,
            item.location_path,
        )
        for item in INITIAL_MAPPING_DECISIONS
    }
    assert actual == {
        ("category", "29", "Cement", "approve", "construction", "cement", ()),
        ("category", "36", "Apartments", "approve", "property", "apartments", ()),
        (
            "category",
            "37",
            "Commercial Properties",
            "approve",
            "property",
            "commercial_properties",
            (),
        ),
        ("category", "40", "Furniture", "approve", "home_interior", "furniture", ()),
        ("category", "46", "Architects", "approve", "professional_services", "architects", ()),
        ("category", "47", "Engineers", "approve", "professional_services", "engineers", ()),
        ("category", "62", "Energy Solutions", "approve", "construction", "energy_solutions", ()),
        ("category", "64", "Appliances", "approve", "home_interior", "appliances", ()),
        (
            "category",
            "65",
            "Building Materials",
            "approve",
            "construction",
            "building_materials",
            (),
        ),
        ("category", "66", "Doors", "approve", "construction", "doors", ()),
        ("location", "51", "Kampala", "approve", None, "kampala", ("africa", "uganda", "kampala")),
        ("directory", "3", "Business", "reject", None, None, ()),
    }
    rejection = next(item for item in INITIAL_MAPPING_DECISIONS if item.action == "reject")
    assert rejection.marketplace_code is None
    assert rejection.target_code is None
    assert rejection.location_path == ()


def test_seed_definitions_are_africa_ready_without_defaults() -> None:
    assert len(CATEGORY_NAMES["construction"]) == 21
    assert CATEGORY_NAMES["construction"][-2:] == (
        "Energy Solutions",
        "Building Materials",
    )
    assert (
        LocationSeed("africa", "Africa", None, "AF", "continent"),
        LocationSeed("uganda", "Uganda", "africa", "UG", "country"),
        LocationSeed("kampala", "Kampala", "uganda", "UG", "city"),
    ) == LOCATION_DEFINITIONS
    assert NormalizedListing.model_fields["currency"].default is None
    assert NormalizedListing.model_fields["locations"].is_required()


def test_location_definition_validation_rejects_missing_parent_and_cycles() -> None:
    with pytest.raises(SeedConflictError, match="parent"):
        validate_location_definitions((LocationSeed("city", "City", "missing", "ZZ", "city"),))
    with pytest.raises(SeedConflictError, match="cycle"):
        validate_location_definitions(
            (
                LocationSeed("one", "One", "two", "ZZ", "region"),
                LocationSeed("two", "Two", "one", "ZZ", "region"),
            )
        )


def test_curation_job_has_no_network_or_runtime_decision_input() -> None:
    source = pytest.importorskip("app.jobs.apply_initial_taxonomy_mappings").__file__
    assert source is not None
    tree = ast.parse(Path(source).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(
        name.startswith(("httpx", "requests", "app.integrations.directorist")) for name in imported
    )
    assert not any(
        isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "parse_args"
        for node in ast.walk(tree)
    )
