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
    PaginationDiagnostic,
    PaginationReason,
)
from app.integrations.directorist.schemas import (
    DirectoristCategoryPage,
    DirectoristListingV1,
    DirectoristPage,
    DirectoristValidatedPage,
    ListingValidationFailure,
)

TRANSIENT_STATUSES = {500, 502, 503, 504}
JSON_CONTENT_TYPES = {"application/json", "application/problem+json"}
MAX_SAFE_DIAGNOSTIC_INTEGER = 2_147_483_647


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
        enforce_reported_page_limit: bool = True,
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
        self._enforce_reported_page_limit = enforce_reported_page_limit
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
        total_present, total_valid, total = self._header_state(response.headers, "X-WP-Total")
        pages_present, pages_valid, pages = self._header_state(response.headers, "X-WP-TotalPages")
        diagnostic = self._pagination_diagnostic(
            total_present=total_present,
            total_valid=total_valid,
            total=total,
            pages_present=pages_present,
            pages_valid=pages_valid,
            pages=pages,
            requested_page=page,
            returned_collection_count=len(payload),
        )
        if not total_present:
            self._raise_pagination("missing_total", diagnostic)
        if not total_valid:
            self._raise_pagination("invalid_total", diagnostic)
        if not pages_present:
            self._raise_pagination("missing_total_pages", diagnostic)
        if not pages_valid:
            self._raise_pagination("invalid_total_pages", diagnostic)
        assert total is not None and pages is not None
        if total < 0 or pages < 0:
            self._raise_pagination("negative_metadata", diagnostic)
        if pages == 0 and total > 0:
            self._raise_pagination("zero_pages_with_items", diagnostic)
        if page > max(pages, 1):
            self._raise_pagination("page_exceeds_total_pages", diagnostic)
        if total < len(payload):
            self._raise_pagination("total_below_collection_count", diagnostic)
        if self._enforce_reported_page_limit and pages > self._max_pages:
            self._raise_pagination("total_pages_exceeds_configured_bound", diagnostic)
        next_page = page + 1 if page < pages and page < self._max_pages else None
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

    async def get_categories_page(self, page: int, per_page: int) -> DirectoristCategoryPage:
        """Read a fixed category page, rejecting incomplete or contradictory metadata."""
        if type(page) is not int or not 1 <= page <= self._max_pages:
            raise DirectoristPaginationError("category page is outside configured bounds")
        if type(per_page) is not int or not 1 <= per_page <= self._max_page_size:
            raise DirectoristPaginationError("category page size is outside configured bounds")
        response, payload = await self._get(
            "/listings/categories", {"page": page, "per_page": per_page}
        )
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise DirectoristResponseFormatError("category collection must be an array of objects")
        metadata: list[int] = []
        for header in ("X-WP-Total", "X-WP-TotalPages"):
            value = response.headers.get(header, "")
            if not value or len(value) > 10 or not value.isascii() or not value.isdecimal():
                raise DirectoristPaginationError("category pagination metadata is invalid")
            number = int(value)
            if number > MAX_SAFE_DIAGNOSTIC_INTEGER:
                raise DirectoristPaginationError("category pagination metadata is outside bounds")
            metadata.append(number)
        total, pages = metadata
        expected_pages = (total + per_page - 1) // per_page
        if (
            pages > self._max_pages
            or (total > 0 and pages != expected_pages)
            or (total == 0 and pages not in {0, 1})
            or page > max(pages, 1)
            or len(payload) != min(per_page, max(0, total - (page - 1) * per_page))
        ):
            raise DirectoristPaginationError("category pagination is inconsistent or incomplete")
        identities: set[int] = set()
        for item in payload:
            identity = item.get("id")
            if type(identity) is not int or identity <= 0:
                raise DirectoristResponseFormatError("category identity is invalid")
            if identity in identities:
                raise DirectoristPaginationError("category identities are duplicated")
            identities.add(identity)
        return DirectoristCategoryPage(
            items=payload,
            current_page=page,
            page_size=per_page,
            total_items=total,
            total_pages=pages,
            next_page=page + 1 if page < pages else None,
        )

    async def get_all_categories(self, per_page: int) -> list[dict[str, Any]]:
        """Return categories only after a bounded, consistent traversal completes."""
        first = await self.get_categories_page(1, per_page)
        items = list(first.items)
        seen = {item["id"] for item in items}
        for number in range(2, first.total_pages + 1):
            page = await self.get_categories_page(number, per_page)
            if (page.total_items, page.total_pages) != (first.total_items, first.total_pages):
                raise DirectoristPaginationError("category pagination changed during traversal")
            for item in page.items:
                if item["id"] in seen:
                    raise DirectoristPaginationError("category identities repeat across pages")
                seen.add(item["id"])
                items.append(item)
        if len(items) != first.total_items:
            raise DirectoristPaginationError("category traversal is incomplete")
        return items

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
    def _header_state(headers: httpx.Headers, name: str) -> tuple[bool, bool, int | None]:
        value = headers.get(name)
        if value is None:
            return False, False, None
        try:
            return True, True, int(value)
        except ValueError:
            return True, False, None

    def _pagination_diagnostic(
        self,
        *,
        total_present: bool,
        total_valid: bool,
        total: int | None,
        pages_present: bool,
        pages_valid: bool,
        pages: int | None,
        requested_page: int,
        returned_collection_count: int,
    ) -> PaginationDiagnostic:
        return PaginationDiagnostic(
            total_header_present=total_present,
            total_header_integer_valid=total_valid,
            total_pages_header_present=pages_present,
            total_pages_header_integer_valid=pages_valid,
            reported_total=self._safe_diagnostic_integer(total),
            reported_total_pages=self._safe_diagnostic_integer(pages),
            requested_page=min(max(requested_page, 0), MAX_SAFE_DIAGNOSTIC_INTEGER),
            returned_collection_count=min(
                max(returned_collection_count, 0), MAX_SAFE_DIAGNOSTIC_INTEGER
            ),
            configured_max_pages=min(max(self._max_pages, 1), MAX_SAFE_DIAGNOSTIC_INTEGER),
        )

    @staticmethod
    def _safe_diagnostic_integer(value: int | None) -> int | None:
        if value is None or value < 0 or value > MAX_SAFE_DIAGNOSTIC_INTEGER:
            return None
        return value

    @staticmethod
    def _raise_pagination(reason: PaginationReason, diagnostic: PaginationDiagnostic) -> None:
        raise DirectoristPaginationError(
            "Directorist pagination validation failed",
            reason=reason,
            diagnostic=diagnostic,
        )

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
