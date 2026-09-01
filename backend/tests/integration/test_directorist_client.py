"""Offline HTTPX transport and static safety tests for the GET-only adapter."""

import asyncio
import inspect
import json
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.integrations.directorist.client import DirectoristClient
from app.integrations.directorist.errors import (
    DirectoristContentTypeError,
    DirectoristHTTPError,
    DirectoristJSONError,
    DirectoristPaginationError,
    DirectoristRateLimitError,
    DirectoristRedirectError,
    DirectoristResponseFormatError,
    DirectoristResponseTooLargeError,
    DirectoristSchemaError,
    DirectoristTimeoutError,
    DirectoristUnavailableError,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "directorist_listing_v1.json"
RECORD = json.loads(FIXTURE.read_text(encoding="utf-8"))["records"][0]


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def response(
    request: httpx.Request,
    payload: object = None,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
    content: bytes | None = None,
) -> httpx.Response:
    base = {"content-type": "application/json", "X-WP-Total": "1", "X-WP-TotalPages": "1"}
    base.update(headers or {})
    return (
        httpx.Response(status, request=request, headers=base, json=payload)
        if content is None
        else httpx.Response(status, request=request, headers=base, content=content)
    )


def client(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> DirectoristClient:
    return DirectoristClient(
        base_url="https://source.test",
        transport=httpx.MockTransport(handler),
        retry_delay_seconds=0,
        **kwargs,
    )


def test_page_path_query_headers_and_pagination() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response(
            request,
            [RECORD],
            headers={
                "Link": '<https://evil.test/>; rel="next"',
                "X-WP-TotalPages": "2",
                "X-WP-Total": "2",
            },
        )

    adapter = client(handler)
    page = run(adapter.get_listings_page(1, 20))
    run(adapter.aclose())
    assert page.next_page == 2 and page.total_items == 2
    assert seen[0].method == "GET" and seen[0].url.path.endswith("/listings")
    assert dict(seen[0].url.params) == {"page": "1", "per_page": "20"}
    assert "authorization" not in seen[0].headers and "cookie" not in seen[0].headers


def test_single_and_taxonomy_collection_paths() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return response(request, RECORD if request.url.path.endswith("/900001") else [{"id": 1}])

    adapter = client(handler)
    assert run(adapter.get_listing(900001)).id == 900001
    run(adapter.get_directories())
    run(adapter.get_categories())
    run(adapter.get_locations())
    run(adapter.aclose())
    assert paths == [
        "/wp-json/directorist/v1/listings/900001",
        "/wp-json/directorist/v1/directories",
        "/wp-json/directorist/v1/listings/categories",
        "/wp-json/directorist/v1/listings/locations",
    ]


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (302, DirectoristRedirectError),
        (401, DirectoristHTTPError),
        (403, DirectoristHTTPError),
        (429, DirectoristRateLimitError),
        (404, DirectoristHTTPError),
    ],
)
def test_safe_nonretryable_http_errors(status: int, error: type[Exception]) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response(request, {}, status=status)

    adapter = client(handler)
    with pytest.raises(error) as caught:
        run(adapter.get_listing(1))
    run(adapter.aclose())
    assert calls == 1 and "synthetic@example" not in str(caught.value)


def test_transient_retry_then_success_and_exhaustion() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response(request, RECORD if calls == 2 else {}, status=200 if calls == 2 else 503)

    adapter = client(handler, retry_count=1)
    assert run(adapter.get_listing(1)).id == 900001
    run(adapter.aclose())
    assert calls == 2
    adapter = client(lambda request: response(request, {}, status=503), retry_count=1)
    with pytest.raises(DirectoristHTTPError):
        run(adapter.get_listing(1))
    run(adapter.aclose())


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (httpx.ConnectError("offline"), DirectoristUnavailableError),
        (httpx.ReadTimeout("timeout"), DirectoristTimeoutError),
    ],
)
def test_transport_failures_are_bounded(failure: Exception, error: type[Exception]) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise failure

    adapter = client(handler, retry_count=1)
    with pytest.raises(error):
        run(adapter.get_listing(1))
    run(adapter.aclose())
    assert calls == 2


def test_content_json_shape_size_and_schema_errors_do_not_retry() -> None:
    cases = [
        (
            lambda r: response(r, {}, headers={"content-type": "text/html"}),
            DirectoristContentTypeError,
        ),
        (lambda r: response(r, content=b"not-json"), DirectoristJSONError),
        (lambda r: response(r, []), DirectoristResponseFormatError),
        (lambda r: response(r, {"id": 1}), DirectoristSchemaError),
    ]
    for handler, error in cases:
        adapter = client(handler)
        with pytest.raises(error):
            run(adapter.get_listing(1))
        run(adapter.aclose())
    adapter = client(lambda r: response(r, content=b"{}" * 10), max_response_bytes=5)
    with pytest.raises(DirectoristResponseTooLargeError):
        run(adapter.get_listing(1))
    run(adapter.aclose())


@pytest.mark.parametrize(
    ("headers", "page"),
    [
        ({"X-WP-Total": "-1"}, 1),
        ({"X-WP-Total": "bad"}, 1),
        ({"X-WP-TotalPages": "0"}, 1),
        ({"X-WP-TotalPages": "1"}, 2),
    ],
)
def test_invalid_pagination(headers: dict[str, str], page: int) -> None:
    adapter = client(lambda r: response(r, [RECORD], headers=headers), max_pages=10)
    with pytest.raises(DirectoristPaginationError):
        run(adapter.get_listings_page(page, 1))
    run(adapter.aclose())


@pytest.mark.parametrize(
    ("headers", "page", "payload", "max_pages", "reason"),
    [
        ({"X-WP-TotalPages": "1"}, 1, [RECORD], 10, "missing_total"),
        ({"X-WP-Total": "", "X-WP-TotalPages": "1"}, 1, [RECORD], 10, "invalid_total"),
        (
            {"X-WP-Total": "not-an-integer", "X-WP-TotalPages": "1"},
            1,
            [RECORD],
            10,
            "invalid_total",
        ),
        ({"X-WP-Total": "1"}, 1, [RECORD], 10, "missing_total_pages"),
        ({"X-WP-Total": "1", "X-WP-TotalPages": ""}, 1, [RECORD], 10, "invalid_total_pages"),
        (
            {"X-WP-Total": "1", "X-WP-TotalPages": "not-an-integer"},
            1,
            [RECORD],
            10,
            "invalid_total_pages",
        ),
        ({"X-WP-Total": "-1", "X-WP-TotalPages": "1"}, 1, [RECORD], 10, "negative_metadata"),
        ({"X-WP-Total": "1", "X-WP-TotalPages": "0"}, 1, [RECORD], 10, "zero_pages_with_items"),
        ({"X-WP-Total": "2", "X-WP-TotalPages": "1"}, 2, [RECORD], 10, "page_exceeds_total_pages"),
        (
            {"X-WP-Total": "1", "X-WP-TotalPages": "1"},
            1,
            [RECORD, RECORD],
            10,
            "total_below_collection_count",
        ),
        (
            {"X-WP-Total": "2", "X-WP-TotalPages": "2"},
            1,
            [RECORD],
            1,
            "total_pages_exceeds_configured_bound",
        ),
    ],
)
def test_structured_pagination_reasons_preserve_rejection_behavior(
    headers: dict[str, str],
    page: int,
    payload: list[object],
    max_pages: int,
    reason: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "application/json", **headers},
            json=payload,
        )

    adapter = client(handler, max_pages=max_pages)
    with pytest.raises(DirectoristPaginationError) as caught:
        run(adapter.get_validated_listings_page(page, 2))
    run(adapter.aclose())
    assert caught.value.reason == reason
    diagnostic = caught.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.requested_page == page
    assert diagnostic.returned_collection_count == len(payload)
    assert diagnostic.configured_max_pages == max_pages


def test_excessive_pagination_integer_is_not_copied_to_diagnostic() -> None:
    excessive = str(2**100)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={
                "content-type": "application/json",
                "X-WP-Total": "1",
                "X-WP-TotalPages": excessive,
            },
            json=[RECORD],
        )

    adapter = client(handler, max_pages=1)
    with pytest.raises(DirectoristPaginationError) as caught:
        run(adapter.get_validated_listings_page(1, 2))
    run(adapter.aclose())
    assert caught.value.reason == "total_pages_exceeds_configured_bound"
    assert caught.value.diagnostic is not None
    assert caught.value.diagnostic.total_pages_header_integer_valid is True
    assert caught.value.diagnostic.reported_total_pages is None
    assert excessive not in str(caught.value)


def test_bounds_and_public_surface_are_get_only() -> None:
    adapter = client(lambda r: response(r, [RECORD]), max_pages=2, max_page_size=2)
    for coroutine in (
        adapter.get_listings_page(0, 1),
        adapter.get_listings_page(3, 1),
        adapter.get_listings_page(1, 3),
        adapter.get_listing(0),
    ):
        with pytest.raises((DirectoristPaginationError, DirectoristSchemaError)):
            run(coroutine)
    run(adapter.aclose())
    public = {
        name
        for name, _ in inspect.getmembers(DirectoristClient, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public == {
        "aclose",
        "get_listings_page",
        "get_validated_listings_page",
        "get_listing",
        "get_directories",
        "get_categories",
        "get_locations",
    }


def test_static_package_has_no_auth_database_or_import_request() -> None:
    package = Path(__file__).resolve().parents[2] / "app" / "integrations" / "directorist"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    lowered = source.lower()
    assert "authorization" not in lowered and "app.db" not in source and "sqlalchemy" not in source
    assert (
        ".post(" not in source
        and ".put(" not in source
        and ".patch(" not in source
        and ".delete(" not in source
    )
