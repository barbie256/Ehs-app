"""Synthetic transport regressions; no live endpoint compatibility claim."""

import asyncio
from typing import Any

import httpx
import pytest

from app.integrations.directorist.client import DirectoristClient
from app.integrations.directorist.errors import (
    DirectoristHTTPError,
    DirectoristPaginationError,
    DirectoristResponseFormatError,
)


def test_complete_categories_use_only_fixed_get_pages() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json=[{"id": i, "name": "Synthetic"} for i in ([1, 2] if page == 1 else [3])],
            headers={
                "X-WP-Total": "3",
                "X-WP-TotalPages": "2",
                "Link": '<https://unapproved.invalid/private>; rel="next"',
            },
        )

    async def scenario() -> None:
        async with DirectoristClient(
            base_url="https://source.test", transport=httpx.MockTransport(handler), max_pages=2
        ) as client:
            assert [item["id"] for item in await client.get_all_categories(2)] == [1, 2, 3]

    asyncio.run(scenario())
    assert [dict(r.url.params) for r in requests] == [
        {"page": "1", "per_page": "2"},
        {"page": "2", "per_page": "2"},
    ]
    for request in requests:
        assert request.method == "GET"
        assert request.url.host == "source.test"
        assert request.url.path == "/wp-json/directorist/v1/listings/categories"
        assert "authorization" not in request.headers and "cookie" not in request.headers


@pytest.mark.parametrize("total,pages", [(1, 1), (0, 0), (0, 1)])
def test_single_and_empty(total: int, pages: int) -> None:
    async def scenario() -> None:
        async with DirectoristClient(
            base_url="https://source.test",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json=[{"id": 1}] if total else [],
                    headers={"X-WP-Total": str(total), "X-WP-TotalPages": str(pages)},
                )
            ),
        ) as client:
            assert len(await client.get_all_categories(2)) == total

    asyncio.run(scenario())


@pytest.mark.parametrize("page,size", [(0, 2), (3, 2), (1, 0), (1, 3), (True, 2)])
def test_bounds_before_http(page: int, size: int) -> None:
    async def scenario() -> None:
        async with DirectoristClient(
            base_url="https://source.test",
            max_pages=2,
            max_page_size=2,
            transport=httpx.MockTransport(lambda _: pytest.fail("HTTP must not occur")),
        ) as client:
            with pytest.raises(DirectoristPaginationError):
                await client.get_categories_page(page, size)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "total,pages,items",
    [
        (None, "1", [{"id": 1}]),
        ("1", None, [{"id": 1}]),
        ("private-marker", "1", [{"id": 1}]),
        ("1", "bad", [{"id": 1}]),
        ("-1", "1", []),
        ("2147483648", "1", []),
        ("1", "0", [{"id": 1}]),
        ("0", "2", []),
        ("5", "3", [{"id": 1}, {"id": 2}]),
        ("3", "1", [{"id": 1}, {"id": 2}]),
        ("3", "2", [{"id": 1}]),
        ("1", "1", [{"id": 1}, {"id": 2}]),
        ("2", "1", [{"id": 1}, {"id": 1}]),
        ("1", "1", [{"id": True}]),
        ("1", "1", [{"id": "private-marker"}]),
    ],
)
def test_invalid_page_is_controlled(
    total: str | None, pages: str | None, items: list[dict[str, Any]]
) -> None:
    headers = {
        key: value
        for key, value in (("X-WP-Total", total), ("X-WP-TotalPages", pages))
        if value is not None
    }

    async def scenario() -> None:
        async with DirectoristClient(
            base_url="https://source.test",
            max_pages=2,
            enforce_reported_page_limit=False,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=items, headers=headers)
            ),
        ) as client:
            with pytest.raises(
                (DirectoristPaginationError, DirectoristResponseFormatError)
            ) as error:
                await client.get_all_categories(2)
            assert "private-marker" not in str(error.value)

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "duplicate", "changed", "empty"])
def test_later_page_failure(failure: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        first = request.url.params["page"] == "1"
        if not first and failure == "http":
            return httpx.Response(503, json={"private-marker": "never expose"})
        return httpx.Response(
            200,
            json=[{"id": 1}, {"id": 2}]
            if first
            else (
                []
                if failure == "empty"
                else [{"id": 1}]
                if failure == "duplicate"
                else [{"id": 3}, {"id": 4}]
            ),
            headers={
                "X-WP-Total": "4" if not first and failure == "changed" else "3",
                "X-WP-TotalPages": "2",
            },
        )

    async def scenario() -> None:
        async with DirectoristClient(
            base_url="https://source.test", transport=httpx.MockTransport(handler), retry_count=2
        ) as client:
            with pytest.raises((DirectoristHTTPError, DirectoristPaginationError)) as error:
                await client.get_all_categories(2)
            assert "private-marker" not in str(error.value)

    asyncio.run(scenario())
    assert calls == (4 if failure == "http" else 2)


def test_request_beyond_reported_pages() -> None:
    async def scenario() -> None:
        async with DirectoristClient(
            base_url="https://source.test",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json=[], headers={"X-WP-Total": "1", "X-WP-TotalPages": "1"}
                )
            ),
        ) as client:
            with pytest.raises(DirectoristPaginationError):
                await client.get_categories_page(2, 2)

    asyncio.run(scenario())
