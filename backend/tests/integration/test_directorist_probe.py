"""Offline behavior tests for the durable read-only probe."""

import asyncio
import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.integrations.directorist.client import DirectoristClient
from app.jobs import probe_directorist_readonly as probe

FIXTURE = Path(__file__).parents[1] / "fixtures" / "directorist_listing_v1.json"
LISTING = json.loads(FIXTURE.read_text(encoding="utf-8"))["records"][0]


class TrackingTransport(httpx.MockTransport):
    def __init__(self, handler: Any) -> None:
        super().__init__(handler)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True
        await super().aclose()


def response_for(request: httpx.Request, payload: object | None = None) -> httpx.Response:
    if payload is None:
        payload = [LISTING] if request.url.path.endswith("/listings") else [{"id": 1}]
    headers = {"content-type": "application/json"}
    if request.url.path.endswith("/listings"):
        headers.update({"X-WP-Total": "1", "X-WP-TotalPages": "1"})
    return httpx.Response(200, json=payload, headers=headers, request=request)


def execute(
    handler: Any = response_for,
    **options: Any,
) -> tuple[int, list[dict[str, Any]], TrackingTransport, str]:
    stream = io.StringIO()
    transport = TrackingTransport(handler)
    emitter = options.pop("emitter", probe.JsonLineEmitter(stream))
    code = asyncio.run(
        probe.run_probe(
            inner_transport=transport,
            emitter=emitter,
            **options,
        )
    )
    output = stream.getvalue()
    events = [json.loads(line) for line in output.splitlines()]
    return code, events, transport, output


def test_complete_success_has_exact_events_counts_and_closure() -> None:
    code, events, transport, _ = execute()
    assert code == 0
    assert events[0] == {"event": "probe_started"}
    assert events[-1] == {
        "attempted": 4,
        "cleanup_failed": False,
        "event": "probe_finished",
        "exit_code": 0,
        "normalized": 1,
        "rejected": 0,
        "responses_received": 4,
        "status": "succeeded",
        "successful_endpoints": 4,
        "validated": 4,
    }
    assert [event["event"] for event in events].count("endpoint_attempt") == 4
    assert [event["event"] for event in events].count("endpoint_completed") == 4
    assert transport.closed


def test_failure_before_client_construction_still_finishes() -> None:
    def fail_factory(_: probe.GuardedProbeTransport) -> probe.ProbeClient:
        raise RuntimeError("synthetic")

    code, events, transport, _ = execute(client_factory=fail_factory)
    assert code == 13
    assert [event["event"] for event in events] == ["probe_started", "probe_finished"]
    assert events[-1]["attempted"] == 0
    assert transport.closed is True


def test_failure_before_request_one_has_zero_transport_attempts() -> None:
    class PreflightFailureClient:
        def __init__(self, transport: probe.GuardedProbeTransport) -> None:
            self.transport = transport

        async def get_directories(self) -> list[dict[str, Any]]:
            raise RuntimeError("synthetic preflight")

        async def get_categories(self) -> list[dict[str, Any]]:
            return []

        async def get_locations(self) -> list[dict[str, Any]]:
            return []

        async def get_validated_listings_page(self, page: int, per_page: int):  # type: ignore[no-untyped-def]
            raise AssertionError("must not run")

        async def aclose(self) -> None:
            await self.transport.aclose()

    code, events, transport, output = execute(client_factory=PreflightFailureClient)
    assert code == 13
    failed = next(event for event in events if event["event"] == "endpoint_failed")
    assert failed["stage"] == "attempted_no_response"
    assert events[-1]["attempted"] == 0
    assert "synthetic preflight" not in output
    assert transport.closed


@pytest.mark.parametrize("failure_attempt", [1, 2, 3, 4])
def test_failure_during_each_request_is_observable(failure_attempt: int) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == failure_attempt:
            raise httpx.ConnectError("synthetic", request=request)
        return response_for(request)

    code, events, transport, _ = execute(handler)
    assert code == 12
    failed = next(event for event in events if event["event"] == "endpoint_failed")
    assert failed["attempt"] == failure_attempt
    assert failed["stage"] == "attempted_no_response"
    assert events[-1]["attempted"] == failure_attempt
    assert events[-1]["responses_received"] == failure_attempt - 1
    assert events[-1]["successful_endpoints"] == failure_attempt - 1
    assert transport.closed


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_failures_are_controlled(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"synthetic": True},
            headers={"content-type": "application/json"},
            request=request,
        )

    code, events, _, _ = execute(handler)
    assert code == 12
    assert events[-1]["attempted"] == 1
    assert events[-1]["responses_received"] == 1
    assert events[-1]["rejected"] == 1
    assert any(event.get("stage") == "response_rejected" for event in events)


@pytest.mark.parametrize(
    ("handler", "stage"),
    [
        (
            lambda request: httpx.Response(
                302, headers={"location": "https://example.invalid"}, request=request
            ),
            "response_rejected",
        ),
        (
            lambda request: httpx.Response(
                200, text="synthetic", headers={"content-type": "text/plain"}, request=request
            ),
            "response_rejected",
        ),
        (
            lambda request: httpx.Response(
                200,
                content=b"x" * (probe.MAX_RESPONSE_BYTES + 1),
                headers={"content-type": "application/json"},
                request=request,
            ),
            "response_rejected",
        ),
        (
            lambda request: httpx.Response(
                200, content=b"{", headers={"content-type": "application/json"}, request=request
            ),
            "validation_failed",
        ),
        (
            lambda request: response_for(request, {"not": "a collection"}),
            "validation_failed",
        ),
    ],
)
def test_rejected_responses_fail_closed(handler: Any, stage: str) -> None:
    code, events, transport, _ = execute(handler)
    assert code == 12
    assert any(event.get("stage") == stage for event in events)
    assert events[-1]["successful_endpoints"] == 0
    assert transport.closed


def test_listing_validation_failure_is_controlled() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = (
            [{"id": 9, "name": "invalid"}]
            if request.url.path.endswith("/listings")
            else [{"id": 1}]
        )
        return response_for(request, payload)

    code, events, _, output = execute(handler)
    assert code == 12
    assert any(event.get("stage") == "validation_failed" for event in events)
    assert "invalid" not in output


def test_listing_normalization_failure_is_controlled() -> None:
    def fail_mapper(_: Any, __: probe.PendingResolver) -> Any:
        raise RuntimeError("private synthetic value")

    code, events, _, output = execute(mapper=fail_mapper)
    assert code == 12
    assert any(event.get("stage") == "normalization_failed" for event in events)
    assert "private synthetic value" not in output


def test_overall_deadline_is_controlled() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return response_for(request)

    code, events, transport, _ = execute(handler, total_timeout_seconds=0.001)
    assert code == 12
    assert events[-1]["exit_code"] == 12
    assert any(event.get("error_code") == "total_deadline" for event in events)
    assert transport.closed


def test_per_request_timeout_is_controlled_without_retry() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("synthetic", request=request)

    code, events, transport, _ = execute(handler)
    assert code == 12
    assert attempts == 1
    assert events[-1]["attempted"] == 1
    assert events[-1]["responses_received"] == 0
    assert transport.closed


def test_cleanup_failure_cannot_suppress_finish() -> None:
    class CleanupFailureClient:
        def __init__(self, transport: probe.GuardedProbeTransport) -> None:
            self.delegate = DirectoristClient(
                base_url=probe.BASE_URL,
                retry_count=0,
                max_pages=1,
                max_page_size=2,
                transport=transport,
            )

        async def get_directories(self) -> list[dict[str, Any]]:
            return await self.delegate.get_directories()

        async def get_categories(self) -> list[dict[str, Any]]:
            return await self.delegate.get_categories()

        async def get_locations(self) -> list[dict[str, Any]]:
            return await self.delegate.get_locations()

        async def get_validated_listings_page(self, page: int, per_page: int):  # type: ignore[no-untyped-def]
            return await self.delegate.get_validated_listings_page(page, per_page)

        async def aclose(self) -> None:
            await self.delegate.aclose()
            raise RuntimeError("synthetic cleanup")

    code, events, transport, output = execute(client_factory=CleanupFailureClient)
    assert code == 13
    assert events[-1]["cleanup_failed"] is True
    assert events[-1]["event"] == "probe_finished"
    assert "synthetic cleanup" not in output
    assert transport.closed


def test_serialization_fallback_keeps_every_line_json() -> None:
    calls = 0

    def flaky_serializer(*args: Any, **kwargs: Any) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TypeError("synthetic")
        return json.dumps(*args, **kwargs)

    stream = io.StringIO()
    emitter = probe.JsonLineEmitter(stream, flaky_serializer)
    transport = TrackingTransport(response_for)
    code = asyncio.run(probe.run_probe(inner_transport=transport, emitter=emitter))
    assert code == 0
    parsed = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert parsed[0]["event"] == "probe_started"
    assert parsed[-1]["event"] == "probe_finished"
    assert transport.closed


def test_event_allowlists_and_private_output_absence() -> None:
    _, events, _, output = execute()
    for event in events:
        assert set(event) <= probe.EVENT_KEYS[event["event"]]
    lowered = output.lower()
    for prohibited in (
        "sample construction material",
        "synthetic address",
        "permalink",
        "author",
        "description",
        "email",
        "phone",
        "image",
        "https://",
        "wp-json",
    ):
        assert prohibited not in lowered


def test_guard_rejects_wrong_method_host_path_and_fifth_request() -> None:
    async def exercise() -> None:
        inner = TrackingTransport(response_for)
        guarded = probe.GuardedProbeTransport(inner)
        invalid = [
            httpx.Request("POST", probe.BASE_URL + "/wp-json/directorist/v1/directories"),
            httpx.Request("GET", "https://example.invalid/wp-json/directorist/v1/directories"),
            httpx.Request("GET", probe.BASE_URL + "/wp-json/directorist/v1/users"),
            httpx.Request(
                "GET",
                probe.BASE_URL + "/wp-json/directorist/v1/directories",
                headers={"Authorization": "synthetic"},
            ),
            httpx.Request(
                "GET",
                probe.BASE_URL + "/wp-json/directorist/v1/directories",
                headers={"Cookie": "synthetic"},
            ),
        ]
        for request in invalid:
            with pytest.raises(DirectoristResponseFormatError):
                await guarded.handle_async_request(request)
        fresh = probe.GuardedProbeTransport(TrackingTransport(response_for))
        request = httpx.Request("GET", probe.BASE_URL + "/wp-json/directorist/v1/directories")
        for _ in range(4):
            await fresh.handle_async_request(request)
        with pytest.raises(DirectoristResponseFormatError):
            await fresh.handle_async_request(request)
        assert fresh.attempted == 4
        await fresh.aclose()

    from app.integrations.directorist.errors import DirectoristResponseFormatError

    asyncio.run(exercise())
