"""Development-only browser CORS boundary tests."""

import asyncio
import logging
from collections.abc import Mapping

import httpx
import pytest
from fastapi.routing import APIRoute

from app.api.catalogue import router as catalogue_router
from app.core.config import Settings
from app.main import DEVELOPMENT_WEB_ORIGINS, create_app


def settings(environment: str) -> Settings:
    """Build safe, explicit settings without reading private configuration."""
    database_host = "database.example.invalid" if environment == "production" else "localhost"
    return Settings(
        APP_ENV=environment,
        DATABASE_URL=f"postgresql://local-user:placeholder@{database_host}:5432/ehs_test",
        DIRECTORIST_BASE_URL=(
            "http://directorist.test" if environment == "test" else "https://ehsmall.com"
        ),
    )


def request(
    monkeypatch: pytest.MonkeyPatch,
    *,
    environment: str,
    method: str = "GET",
    origin: str = DEVELOPMENT_WEB_ORIGINS[0],
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    """Issue one in-process request without opening a socket or database connection."""
    configured = settings(environment)
    monkeypatch.setattr("app.main.get_settings", lambda: configured)

    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(
                method,
                "/",
                headers={"Origin": origin, **dict(headers or {})},
            )

    return asyncio.run(send())


@pytest.mark.parametrize("origin", DEVELOPMENT_WEB_ORIGINS)
def test_approved_development_origin_is_returned_exactly(
    monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    response = request(monkeypatch, environment="development", origin=origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in response.headers


def test_approved_get_preflight_is_narrow(monkeypatch: pytest.MonkeyPatch) -> None:
    response = request(
        monkeypatch,
        environment="development",
        method="OPTIONS",
        headers={
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Accept",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DEVELOPMENT_WEB_ORIGINS[0]
    assert response.headers["access-control-allow-methods"] == "GET, OPTIONS"
    assert "access-control-allow-credentials" not in response.headers


def test_unknown_origin_receives_no_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    response = request(
        monkeypatch,
        environment="development",
        origin="http://unknown.invalid:8081",
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutating_methods_fail_preflight(monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    response = request(
        monkeypatch,
        environment="development",
        method="OPTIONS",
        headers={"Access-Control-Request-Method": method},
    )

    assert response.status_code == 400


@pytest.mark.parametrize("environment", ["test", "staging", "production"])
def test_non_development_environments_have_no_local_cors_policy(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    response = request(monkeypatch, environment=environment)

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_application_construction_does_not_create_database_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.get_settings", lambda: settings("development"))
    monkeypatch.setattr(
        "app.api.catalogue.create_database_engine",
        lambda *_args, **_kwargs: pytest.fail("database engine created during startup"),
    )

    application = create_app()

    assert application.title == "EHS Mall API"
    api_methods = {
        method
        for route in catalogue_router.routes
        if isinstance(route, APIRoute)
        for method in (route.methods or set())
    }
    assert api_methods == {"GET"}


def test_cors_does_not_log_request_or_private_values(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    private_sentinel = "private-cors-sentinel"
    caplog.set_level(logging.DEBUG)

    response = request(
        monkeypatch,
        environment="development",
        origin=f"http://{private_sentinel}.invalid:8081",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    assert private_sentinel not in caplog.text
    assert response.text not in caplog.text
