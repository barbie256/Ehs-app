"""Constrained asynchronous GET-only Directorist v1 client."""

import asyncio
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

import httpx
from pydantic import ValidationError

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
from app.integrations.directorist.schemas import (
    DirectoristListingV1,
    DirectoristPage,
    DirectoristValidatedPage,
    ListingValidationFailure,
)

TRANSIENT_STATUSES = {500, 502, 503, 504}
JSON_CONTENT_TYPES = {"application/json", "application/problem+json"}


class DirectoristClient:
    """Expose only audited Directorist reads; arbitrary methods and paths are impossible."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10,
        max_pages: int = 100,
        max_page_size: int = 100,
        max_response_bytes: int = 2_000_000,
        retry_count: int = 2,
        retry_delay_seconds: float = 0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = httpx.URL(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.host or parsed.userinfo:
            raise ValueError("Directorist base URL is invalid")
        self._root = str(parsed).rstrip("/") + "/wp-json/directorist/v1"
        self._timeout = httpx.Timeout(
            timeout_seconds,
            connect=timeout_seconds,
            read=timeout_seconds,
            write=timeout_seconds,
            pool=timeout_seconds,
        )
        self._max_pages = max_pages
        self._max_page_size = max_page_size
        self._max_response_bytes = max_response_bytes
        self._retry_count = retry_count
        self._retry_delay = retry_delay_seconds
        self._client = httpx.AsyncClient(
            transport=transport, follow_redirects=False, cookies=None, trust_env=False
        )

    async def __aenter__(self) -> DirectoristClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_listings_page(
        self, page: int, per_page: int, modified_after: datetime | None = None
    ) -> DirectoristPage:
        validated = await self.get_validated_listings_page(page, per_page, modified_after)
        if validated.failures:
            raise DirectoristSchemaError("Directorist listing failed schema validation")
        return DirectoristPage(
            items=validated.items,
            current_page=validated.current_page,
            page_size=validated.page_size,
            total_items=validated.total_items,
            total_pages=validated.total_pages,
            next_page=validated.next_page,
        )

    async def get_validated_listings_page(
        self, page: int, per_page: int, modified_after: datetime | None = None
    ) -> DirectoristValidatedPage:
        """Read a page while returning only redacted identities for malformed members."""
        if page < 1 or page > self._max_pages:
            raise DirectoristPaginationError("page is outside configured bounds")
        if per_page < 1 or per_page > self._max_page_size:
            raise DirectoristPaginationError("page size is outside configured bounds")
        params: dict[str, str | int] = {"page": page, "per_page": per_page}
        if modified_after:
            params["modified_after"] = modified_after.isoformat()
        response, payload = await self._get("/listings", params)
        if not isinstance(payload, list):
            raise DirectoristResponseFormatError("listing collection must be an array")
        items: list[DirectoristListingV1] = []
        failures: list[ListingValidationFailure] = []
        for raw in payload:
            if not isinstance(raw, dict):
                failures.append(ListingValidationFailure(external_id="unknown"))
                continue
            try:
                items.append(self._parse_listing(raw))
            except DirectoristSchemaError:
                candidate = raw.get("id")
                safe_id = (
                    str(candidate) if isinstance(candidate, int) and candidate > 0 else "unknown"
                )
                failures.append(ListingValidationFailure(external_id=safe_id))
        total = self._header_int(response.headers, "X-WP-Total")
        pages = self._header_int(response.headers, "X-WP-TotalPages")
        if total < 0 or pages < 0 or (pages == 0 and total > 0) or page > max(pages, 1):
            raise DirectoristPaginationError("pagination metadata is contradictory")
        if total < len(payload) or pages > self._max_pages:
            raise DirectoristPaginationError("pagination metadata exceeds safe bounds")
        next_page = page + 1 if page < pages else None
        return DirectoristValidatedPage(
            items=items,
            failures=failures,
            current_page=page,
            page_size=per_page,
            total_items=total,
            total_pages=pages,
            next_page=next_page,
        )

    async def get_listing(self, external_id: int) -> DirectoristListingV1:
        if external_id < 1:
            raise DirectoristSchemaError("external listing ID must be positive")
        _, payload = await self._get(f"/listings/{external_id}")
        if not isinstance(payload, dict):
            raise DirectoristResponseFormatError("listing response must be an object")
        return self._parse_listing(payload)

    async def get_directories(self) -> list[dict[str, Any]]:
        return await self._get_collection("/directories")

    async def get_categories(self) -> list[dict[str, Any]]:
        return await self._get_collection("/listings/categories")

    async def get_locations(self) -> list[dict[str, Any]]:
        return await self._get_collection("/listings/locations")

    async def _get_collection(self, path: str) -> list[dict[str, Any]]:
        _, payload = await self._get(path)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise DirectoristResponseFormatError("collection response must be an array of objects")
        return payload

    async def _get(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> tuple[httpx.Response, object]:
        for attempt in range(self._retry_count + 1):
            try:
                response = await self._client.get(
                    self._root + path,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "EHS-Mall-ReadOnly-Adapter/1.0",
                    },
                    timeout=self._timeout,
                    follow_redirects=False,
                )
            except httpx.TimeoutException:
                if attempt < self._retry_count:
                    await asyncio.sleep(self._retry_delay)
                    continue
                raise DirectoristTimeoutError() from None
            except httpx.ConnectError:
                if attempt < self._retry_count:
                    await asyncio.sleep(self._retry_delay)
                    continue
                raise DirectoristUnavailableError() from None
            if 300 <= response.status_code < 400:
                raise DirectoristRedirectError()
            if response.status_code == 429:
                raise DirectoristRateLimitError()
            if response.status_code in TRANSIENT_STATUSES and attempt < self._retry_count:
                await asyncio.sleep(self._retry_delay)
                continue
            if response.status_code >= 400:
                raise DirectoristHTTPError(f"Directorist returned HTTP {response.status_code}")
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type not in JSON_CONTENT_TYPES and not content_type.endswith("+json"):
                raise DirectoristContentTypeError()
            if len(response.content) > self._max_response_bytes:
                raise DirectoristResponseTooLargeError()
            try:
                return response, json.loads(response.content)
            except UnicodeDecodeError, json.JSONDecodeError:
                raise DirectoristJSONError() from None
        raise DirectoristUnavailableError()

    @staticmethod
    def _header_int(headers: httpx.Headers, name: str) -> int:
        try:
            return int(headers[name])
        except KeyError, ValueError:
            raise DirectoristPaginationError(f"{name} is missing or invalid") from None

    def _parse_listings(self, payload: list[object]) -> list[DirectoristListingV1]:
        if not all(isinstance(item, dict) for item in payload):
            raise DirectoristResponseFormatError("listing array contains a non-object")
        return [self._parse_listing(cast(dict[str, object], item)) for item in payload]

    @staticmethod
    def _parse_listing(payload: Mapping[str, object]) -> DirectoristListingV1:
        try:
            return DirectoristListingV1.model_validate(payload)
        except ValidationError:
            raise DirectoristSchemaError("Directorist listing failed schema validation") from None
