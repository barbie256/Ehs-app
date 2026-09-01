"""Malformed listing members do not invalidate valid siblings for sync callers."""

import asyncio
import json
from pathlib import Path

import httpx

from app.integrations.directorist.client import DirectoristClient


def test_validated_page_redacts_and_isolates_invalid_member() -> None:
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "directorist_listing_v1.json").read_text()
    )
    valid = fixture["records"][0]
    invalid = {"id": 900002, "name": "missing required safe fields"}

    async def exercise() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={
                    "content-type": "application/json",
                    "X-WP-Total": "2",
                    "X-WP-TotalPages": "1",
                },
                json=[valid, invalid],
                request=request,
            )

        async with DirectoristClient(
            base_url="https://example.invalid", transport=httpx.MockTransport(handler)
        ) as client:
            page = await client.get_validated_listings_page(1, 20)
        assert [item.id for item in page.items] == [900001]
        assert page.failures[0].model_dump() == {
            "external_id": "900002",
            "error_code": "invalid_listing_schema",
            "field_summary": "listing",
        }

    asyncio.run(exercise())
