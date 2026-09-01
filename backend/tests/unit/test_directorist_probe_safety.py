"""Static immutability and no-side-effect guarantees for the probe module."""

import ast
import json
import subprocess
import sys
from pathlib import Path

from app.jobs import probe_directorist_readonly as probe

MODULE = Path(probe.__file__).resolve()


def test_frozen_host_paths_and_request_limits() -> None:
    assert probe.BASE_URL == "https://ehsmall.com"
    assert probe.APPROVED_HOST == "ehsmall.com"
    assert probe.MAX_REQUESTS == 4
    assert set(probe.APPROVED_PATHS) == {
        "/wp-json/directorist/v1/directories",
        "/wp-json/directorist/v1/listings/categories",
        "/wp-json/directorist/v1/listings/locations",
        "/wp-json/directorist/v1/listings",
    }
    assert probe.TOTAL_TIMEOUT_SECONDS == 45.0


def test_no_database_sync_or_unsafe_http_imports() -> None:
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    prohibited = {"sqlalchemy", "app.db", "app.repositories", "app.services.catalogue_sync"}
    assert not any(any(name.startswith(prefix) for prefix in prohibited) for name in imports)
    lowered = source.lower()
    assert "/users" not in lowered
    assert ".post(" not in lowered and ".put(" not in lowered and ".patch(" not in lowered
    assert "authorization=" not in lowered and "cookies=" not in lowered
    assert "retry_count=0" in source
    assert "max_pages=1" in source
    assert "enforce_reported_page_limit=False" in source


def test_import_performs_no_work_or_output() -> None:
    result = subprocess.run(
        [sys.executable, "-B", "-c", "import app.jobs.probe_directorist_readonly"],
        cwd=MODULE.parents[3],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == "" and result.stderr == ""


def test_event_key_sets_are_json_safe_and_private_free() -> None:
    keys = set().union(*probe.EVENT_KEYS.values())
    assert not keys.intersection(
        {"title", "description", "address", "email", "phone", "url", "headers", "id"}
    )
    json.dumps({key: sorted(value) for key, value in probe.EVENT_KEYS.items()})
    assert {
        "failure_category",
        "pagination_reason",
        "total_header_present",
        "total_header_integer_valid",
        "total_pages_header_present",
        "total_pages_header_integer_valid",
        "reported_total",
        "reported_total_pages",
        "requested_page",
        "returned_collection_count",
        "configured_max_pages",
    } <= probe.EVENT_KEYS["endpoint_failed"]


def test_validation_diagnostics_copy_only_location_and_type() -> None:
    source = MODULE.read_text(encoding="utf-8")
    assert 'detail.get("loc")' in source
    assert 'detail.get("type")' in source
    for prohibited in (
        'detail["input"]',
        'detail.get("input")',
        'detail["msg"]',
        'detail.get("msg")',
        'detail["url"]',
        'detail.get("url")',
        "str(validation_exception)",
        "repr(validation_exception)",
    ):
        assert prohibited not in source
    assert probe.MAX_DIAGNOSTIC_ENTRIES == 20
    assert probe.MAX_DIAGNOSTIC_OUTPUT_BYTES <= 6_000
    assert probe.MAX_FIELD_PATH_LENGTH <= 120
    assert probe.MAX_ERROR_TYPE_LENGTH <= 64
