"""Durable, observable, database-free Directorist read-only probe."""

import asyncio
import json
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TextIO

import httpx

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
    "endpoint_failed": frozenset({"event", "endpoint", "attempt", "stage", "error_code"}),
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


class GuardedProbeTransport(httpx.AsyncBaseTransport):
    """Constrain and observe an injected HTTPX transport without retaining source data."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.attempted = 0
        self.responses_received = 0
        self.rejected = 0
        self.last_metric: ResponseMetric | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_metric = None
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
                    output.emit(
                        "endpoint_failed",
                        endpoint=endpoint,
                        attempt=current_attempt,
                        stage=stage,
                        error_code=code,
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
