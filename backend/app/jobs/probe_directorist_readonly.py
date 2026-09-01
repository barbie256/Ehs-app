"""Durable, observable, database-free Directorist read-only probe."""

import asyncio
import json
import re
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TextIO

import httpx
from pydantic import ValidationError

from app.integrations.directorist.client import DirectoristClient
from app.integrations.directorist.errors import (
    DirectoristError,
    DirectoristJSONError,
    DirectoristMappingError,
    DirectoristPaginationError,
    DirectoristResponseFormatError,
    DirectoristSchemaError,
)
from app.integrations.directorist.mapper import map_listing, to_summary
from app.integrations.directorist.schemas import DirectoristListingV1, SourceImage, SourceTaxonomy
from app.schemas.catalogue import CanonicalMapping, NormalizedListing

BASE_URL = "https://ehsmall.com"
APPROVED_HOST = "ehsmall.com"
API_PREFIX = "/wp-json/directorist/v1/"
APPROVED_PATHS: Mapping[str, str] = {
    "/wp-json/directorist/v1/directories": "directories",
    "/wp-json/directorist/v1/listings/categories": "listings/categories",
    "/wp-json/directorist/v1/listings/locations": "listings/locations",
    "/wp-json/directorist/v1/listings": "listings",
}
MAX_REQUESTS = 4
MAX_RESPONSE_BYTES = 2_000_000
REQUEST_TIMEOUT_SECONDS = 10.0
TOTAL_TIMEOUT_SECONDS = 45.0
MAX_DIAGNOSTIC_ENTRIES = 20
MAX_DIAGNOSTIC_OUTPUT_BYTES = 6_000
MAX_FIELD_PATH_LENGTH = 120
MAX_ERROR_TYPE_LENGTH = 64
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_]+$")
SAFE_ERROR_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

EXIT_SUCCESS = 0
EXIT_CONTROLLED_FAILURE = 12
EXIT_INTERNAL_FAILURE = 13

EVENT_KEYS: Mapping[str, frozenset[str]] = {
    "probe_started": frozenset({"event"}),
    "endpoint_attempt": frozenset({"event", "endpoint", "attempt"}),
    "endpoint_completed": frozenset(
        {
            "event",
            "endpoint",
            "attempt",
            "duration_ms",
            "response_bytes",
            "item_count",
            "total",
            "total_pages",
            "validation_count",
            "normalization_count",
            "currency_null",
            "summary_private_fields_excluded",
        }
    ),
    "endpoint_failed": frozenset(
        {
            "event",
            "endpoint",
            "attempt",
            "stage",
            "error_code",
            "response_byte_count",
            "collection_item_count",
            "failed_validation_count",
            "total_validation_errors",
            "validation_diagnostics",
            "diagnostics_truncated",
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
        }
    ),
    "probe_finished": frozenset(
        {
            "event",
            "attempted",
            "responses_received",
            "rejected",
            "validated",
            "normalized",
            "successful_endpoints",
            "status",
            "exit_code",
            "cleanup_failed",
        }
    ),
}
SAFE_STAGES = {
    "attempted_no_response",
    "response_rejected",
    "validation_failed",
    "normalization_failed",
}


class ProbeClient(Protocol):
    async def get_directories(self) -> list[dict[str, Any]]: ...

    async def get_categories(self) -> list[dict[str, Any]]: ...

    async def get_locations(self) -> list[dict[str, Any]]: ...

    async def get_validated_listings_page(self, page: int, per_page: int): ...  # type: ignore[no-untyped-def]

    async def aclose(self) -> None: ...


class PendingResolver:
    """Resolve nothing and perform no database or network access."""

    def resolve_category(self, external_id: int) -> CanonicalMapping | None:
        return None


class JsonLineEmitter:
    def __init__(
        self,
        stream: TextIO,
        serializer: Callable[..., str] = json.dumps,
    ) -> None:
        self._stream = stream
        self._serializer = serializer

    def emit(self, event: str, **values: object) -> None:
        allowed = EVENT_KEYS[event]
        payload: dict[str, object] = {"event": event}
        payload.update({key: value for key, value in values.items() if key in allowed})
        try:
            line = self._serializer(payload, sort_keys=True, separators=(",", ":"))
        except Exception:
            line = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        print(line, file=self._stream, flush=True)


@dataclass
class ResponseMetric:
    endpoint: str
    duration_ms: int
    response_bytes: int
    total: int | None
    total_pages: int | None


@dataclass(frozen=True)
class SafeValidationDiagnostic:
    sample_position: int
    field_path: str
    error_type: str
    occurrence_count: int


@dataclass(frozen=True)
class SafeValidationSummary:
    collection_item_count: int
    failed_validation_count: int
    total_validation_errors: int
    diagnostics: tuple[SafeValidationDiagnostic, ...]
    truncated: bool


class GuardedProbeTransport(httpx.AsyncBaseTransport):
    """Constrain and observe an injected HTTPX transport without retaining source data."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.attempted = 0
        self.responses_received = 0
        self.rejected = 0
        self.last_metric: ResponseMetric | None = None
        self.last_validation_summary: SafeValidationSummary | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_metric = None
        self.last_validation_summary = None
        if self.attempted >= MAX_REQUESTS:
            self.rejected += 1
            raise DirectoristResponseFormatError("probe request limit exceeded")
        self.attempted += 1
        self._validate_request(request)
        started = time.perf_counter()
        response = await self._inner.handle_async_request(request)
        self.responses_received += 1
        duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        if 300 <= response.status_code < 400:
            self.rejected += 1
            raise DirectoristResponseFormatError("probe redirect rejected")
        content = await response.aread()
        if len(content) > MAX_RESPONSE_BYTES:
            self.rejected += 1
            raise DirectoristResponseFormatError("probe response size rejected")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in {
            "application/json",
            "application/problem+json",
        } and not content_type.endswith("+json"):
            self.rejected += 1
            raise DirectoristResponseFormatError("probe content type rejected")
        endpoint = APPROVED_PATHS[request.url.path]
        if endpoint == "listings" and 200 <= response.status_code < 300:
            self.last_validation_summary = _inspect_listing_validation(content)
        self.last_metric = ResponseMetric(
            endpoint=endpoint,
            duration_ms=duration_ms,
            response_bytes=len(content),
            total=self._safe_header(response.headers, "X-WP-Total"),
            total_pages=self._safe_header(response.headers, "X-WP-TotalPages"),
        )
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=content,
            request=request,
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()

    def _validate_request(self, request: httpx.Request) -> None:
        if request.method != "GET":
            self.rejected += 1
            raise DirectoristResponseFormatError("probe method rejected")
        if request.url.scheme != "https" or request.url.host != APPROVED_HOST:
            self.rejected += 1
            raise DirectoristResponseFormatError("probe host rejected")
        if request.url.path not in APPROVED_PATHS:
            self.rejected += 1
            raise DirectoristResponseFormatError("probe path rejected")
        if "authorization" in request.headers or "cookie" in request.headers:
            self.rejected += 1
            raise DirectoristResponseFormatError("probe credential header rejected")
        query = dict(request.url.params)
        expected = {"page": "1", "per_page": "2"} if request.url.path.endswith("/listings") else {}
        if query != expected:
            self.rejected += 1
            raise DirectoristResponseFormatError("probe query rejected")

    @staticmethod
    def _safe_header(headers: httpx.Headers, name: str) -> int | None:
        value = headers.get(name)
        if value is None:
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None


def _declared_names(model: type[Any]) -> frozenset[str]:
    return frozenset(
        {name for name in model.model_fields}
        | {field.alias for field in model.model_fields.values() if isinstance(field.alias, str)}
    )


LISTING_FIELD_NAMES = _declared_names(DirectoristListingV1)
TAXONOMY_FIELD_NAMES = _declared_names(SourceTaxonomy)
IMAGE_FIELD_NAMES = _declared_names(SourceImage)
INDEXED_TAXONOMY_FIELDS = {"categories", "locations", "tags"}


def _safe_field_path(location: tuple[object, ...]) -> str:
    """Convert Pydantic locations to bounded declared-schema paths only."""
    if not location:
        return "record"
    root = location[0]
    if not isinstance(root, str) or root not in LISTING_FIELD_NAMES:
        return "redacted"
    components = [root]
    for index, component in enumerate(location[1:], start=1):
        permitted = False
        if isinstance(component, int) and component >= 0:
            permitted = root in INDEXED_TAXONOMY_FIELDS | {"images", "related_ids"} and index == 1
        elif isinstance(component, str) and SAFE_COMPONENT.fullmatch(component):
            if root in INDEXED_TAXONOMY_FIELDS and index == 2:
                permitted = component in TAXONOMY_FIELD_NAMES
            elif root == "images" and index == 2:
                permitted = component in IMAGE_FIELD_NAMES
        if not permitted:
            components.append("redacted")
            break
        components.append(str(component))
    return ".".join(components)[:MAX_FIELD_PATH_LENGTH]


def _safe_error_type(value: object) -> str:
    if not isinstance(value, str) or len(value) > MAX_ERROR_TYPE_LENGTH:
        return "validation_error"
    return value if SAFE_ERROR_TYPE.fullmatch(value) else "validation_error"


def _group_diagnostics(
    diagnostics: list[tuple[int, str, str]],
) -> tuple[tuple[SafeValidationDiagnostic, ...], bool]:
    grouped: dict[tuple[int, str, str], int] = {}
    for diagnostic in diagnostics:
        grouped[diagnostic] = grouped.get(diagnostic, 0) + 1
    entries = tuple(
        SafeValidationDiagnostic(position, path, error_type, count)
        for (position, path, error_type), count in list(grouped.items())[:MAX_DIAGNOSTIC_ENTRIES]
    )
    return entries, len(grouped) > MAX_DIAGNOSTIC_ENTRIES


def _inspect_listing_validation(content: bytes) -> SafeValidationSummary | None:
    """Copy only Pydantic location/type structure; source objects remain function-local."""
    try:
        payload = json.loads(content)
    except UnicodeDecodeError, json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    diagnostics: list[tuple[int, str, str]] = []
    failed_items = 0
    total_errors = 0
    for position, item in enumerate(payload, start=1):
        try:
            DirectoristListingV1.model_validate(item)
        except ValidationError as validation_exception:
            failed_items += 1
            safe_errors = validation_exception.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )
            total_errors += len(safe_errors)
            for detail in safe_errors:
                location = detail.get("loc")
                safe_location = tuple(location) if isinstance(location, tuple) else ()
                diagnostics.append(
                    (
                        position,
                        _safe_field_path(safe_location),
                        _safe_error_type(detail.get("type")),
                    )
                )
    entries, truncated = _group_diagnostics(diagnostics)
    return SafeValidationSummary(
        collection_item_count=len(payload),
        failed_validation_count=failed_items,
        total_validation_errors=total_errors,
        diagnostics=entries,
        truncated=truncated,
    )


@dataclass
class ProbeState:
    attempted: int = 0
    responses_received: int = 0
    rejected: int = 0
    validated: int = 0
    normalized: int = 0
    successful_endpoints: int = 0
    status: str = "failed"
    exit_code: int = EXIT_INTERNAL_FAILURE
    cleanup_failed: bool = False


ClientFactory = Callable[[GuardedProbeTransport], ProbeClient]
Mapper = Callable[[Any, PendingResolver], NormalizedListing]


def _default_client_factory(transport: GuardedProbeTransport) -> ProbeClient:
    return DirectoristClient(
        base_url=BASE_URL,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        max_pages=1,
        max_page_size=2,
        max_response_bytes=MAX_RESPONSE_BYTES,
        retry_count=0,
        transport=transport,
    )


def _default_transport() -> httpx.AsyncBaseTransport:
    return httpx.AsyncHTTPTransport(retries=0)


async def run_probe(
    *,
    inner_transport: httpx.AsyncBaseTransport | None = None,
    client_factory: ClientFactory = _default_client_factory,
    emitter: JsonLineEmitter | None = None,
    mapper: Mapper = map_listing,
    total_timeout_seconds: float = TOTAL_TIMEOUT_SECONDS,
) -> int:
    """Execute the fixed probe; injection points exist only for deterministic offline tests."""
    output = emitter or JsonLineEmitter(sys.stdout)
    state = ProbeState()
    transport: GuardedProbeTransport | None = None
    client: ProbeClient | None = None
    current_endpoint = "directories"
    current_attempt = 0
    output.emit("probe_started")
    try:
        async with asyncio.timeout(total_timeout_seconds):
            transport = GuardedProbeTransport(inner_transport or _default_transport())
            client = client_factory(transport)
            calls: list[tuple[str, Callable[[], Any]]] = [
                ("directories", client.get_directories),
                ("listings/categories", client.get_categories),
                ("listings/locations", client.get_locations),
                ("listings", lambda: client.get_validated_listings_page(1, 2)),
            ]
            for endpoint, call in calls:
                current_endpoint = endpoint
                current_attempt += 1
                output.emit("endpoint_attempt", endpoint=endpoint, attempt=current_attempt)
                try:
                    result = await call()
                    metric = transport.last_metric
                    if metric is None:
                        raise DirectoristResponseFormatError("probe response metric missing")
                    validation_count, normalization_count, currency_null, private_excluded = (
                        _validate_result(endpoint, result, mapper)
                    )
                except Exception as error:
                    stage, code = _controlled_failure(error, transport)
                    if stage == "response_rejected" and transport.last_metric is not None:
                        transport.rejected += 1
                    diagnostic_values: dict[str, object] = {}
                    if stage == "validation_failed" and endpoint == "listings":
                        diagnostic_values = _diagnostic_event_values(transport, error)
                    output.emit(
                        "endpoint_failed",
                        endpoint=endpoint,
                        attempt=current_attempt,
                        stage=stage,
                        error_code=code,
                        **diagnostic_values,
                    )
                    raise
                state.validated += validation_count
                state.normalized += normalization_count
                state.successful_endpoints += 1
                output.emit(
                    "endpoint_completed",
                    endpoint=endpoint,
                    attempt=current_attempt,
                    duration_ms=metric.duration_ms,
                    response_bytes=metric.response_bytes,
                    item_count=validation_count,
                    total=metric.total,
                    total_pages=metric.total_pages,
                    validation_count=validation_count,
                    normalization_count=normalization_count,
                    currency_null=currency_null,
                    summary_private_fields_excluded=private_excluded,
                )
            state.status = "succeeded"
            state.exit_code = EXIT_SUCCESS
    except TimeoutError:
        output.emit(
            "endpoint_failed",
            endpoint=current_endpoint,
            attempt=current_attempt,
            stage="attempted_no_response",
            error_code="total_deadline",
        )
        state.exit_code = EXIT_CONTROLLED_FAILURE
    except DirectoristError:
        state.exit_code = EXIT_CONTROLLED_FAILURE
    except Exception:
        state.exit_code = EXIT_INTERNAL_FAILURE
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                state.cleanup_failed = True
                state.status = "failed"
                state.exit_code = EXIT_INTERNAL_FAILURE
        elif transport is not None:
            try:
                await transport.aclose()
            except Exception:
                state.cleanup_failed = True
                state.exit_code = EXIT_INTERNAL_FAILURE
        if transport is not None:
            state.attempted = transport.attempted
            state.responses_received = transport.responses_received
            state.rejected = transport.rejected
        output.emit(
            "probe_finished",
            attempted=state.attempted,
            responses_received=state.responses_received,
            rejected=state.rejected,
            validated=state.validated,
            normalized=state.normalized,
            successful_endpoints=state.successful_endpoints,
            status=state.status,
            exit_code=state.exit_code,
            cleanup_failed=state.cleanup_failed,
        )
    return state.exit_code


def _diagnostic_event_values(
    transport: GuardedProbeTransport, error: Exception
) -> dict[str, object]:
    metric = transport.last_metric
    summary = transport.last_validation_summary
    if metric is None or summary is None:
        return {}
    diagnostics = [
        {
            "sample_position": item.sample_position,
            "field_path": item.field_path,
            "error_type": item.error_type,
            "occurrence_count": item.occurrence_count,
        }
        for item in summary.diagnostics
    ]
    size_truncated = False
    while (
        len(json.dumps(diagnostics, separators=(",", ":")).encode()) > MAX_DIAGNOSTIC_OUTPUT_BYTES
    ):
        diagnostics.pop()
        size_truncated = True
    values: dict[str, object] = {
        "response_byte_count": metric.response_bytes,
        "collection_item_count": summary.collection_item_count,
        "failed_validation_count": summary.failed_validation_count,
        "total_validation_errors": summary.total_validation_errors,
        "validation_diagnostics": diagnostics,
        "diagnostics_truncated": summary.truncated or size_truncated,
    }
    if isinstance(error, DirectoristPaginationError):
        values.update(_pagination_event_values(error))
    return values


def _pagination_event_values(error: DirectoristPaginationError) -> dict[str, object]:
    values: dict[str, object] = {
        "failure_category": "pagination",
        "pagination_reason": error.reason,
    }
    diagnostic = error.diagnostic
    if diagnostic is None:
        return values
    values.update(
        {
            "total_header_present": diagnostic.total_header_present,
            "total_header_integer_valid": diagnostic.total_header_integer_valid,
            "total_pages_header_present": diagnostic.total_pages_header_present,
            "total_pages_header_integer_valid": diagnostic.total_pages_header_integer_valid,
            "reported_total": diagnostic.reported_total,
            "reported_total_pages": diagnostic.reported_total_pages,
            "requested_page": diagnostic.requested_page,
            "returned_collection_count": diagnostic.returned_collection_count,
            "configured_max_pages": diagnostic.configured_max_pages,
        }
    )
    return values


def _validate_result(
    endpoint: str, result: object, mapper: Mapper
) -> tuple[int, int, bool | None, bool | None]:
    if endpoint != "listings":
        if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
            raise DirectoristResponseFormatError("probe taxonomy collection invalid")
        return len(result), 0, None, None
    failures = getattr(result, "failures", None)
    items = getattr(result, "items", None)
    if not isinstance(items, list) or not isinstance(failures, list) or failures:
        raise DirectoristSchemaError("probe listing validation failed")
    resolver = PendingResolver()
    currency_null = True
    private_excluded = True
    for item in items:
        try:
            normalized = mapper(item, resolver)
            repeated = mapper(item, resolver)
            summary = to_summary(normalized).model_dump()
        except Exception:
            raise DirectoristMappingError("probe listing normalization failed") from None
        currency_null = currency_null and normalized.currency is None
        private_excluded = private_excluded and not {
            "contacts",
            "source_author_id",
        }.intersection(summary)
        if not normalized.source_checksum:
            raise DirectoristMappingError("probe checksum generation failed")
        if normalized.source_checksum != repeated.source_checksum:
            raise DirectoristMappingError("probe checksum is not deterministic")
    if not currency_null or not private_excluded:
        raise DirectoristMappingError("probe privacy invariant failed")
    return len(items), len(items), currency_null, private_excluded


def _controlled_failure(error: Exception, transport: GuardedProbeTransport) -> tuple[str, str]:
    if transport.rejected:
        return "response_rejected", "response_rejected"
    if transport.last_metric is None and transport.responses_received <= transport.attempted:
        return "attempted_no_response", "upstream_unavailable"
    if isinstance(
        error,
        (
            DirectoristSchemaError,
            DirectoristPaginationError,
            DirectoristJSONError,
            DirectoristResponseFormatError,
        ),
    ):
        return "validation_failed", "schema_validation"
    if isinstance(error, DirectoristMappingError):
        return "normalization_failed", "normalization"
    if isinstance(error, DirectoristError):
        return "response_rejected", error.code
    return "normalization_failed", "controlled_internal"


def main() -> int:
    return asyncio.run(run_probe())


if __name__ == "__main__":
    raise SystemExit(main())
