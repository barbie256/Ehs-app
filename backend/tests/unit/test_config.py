"""Gate 2 configuration and application tests."""

import asyncio

import httpx
import pytest

from app.core.config import AppEnvironment, Settings, SettingsConfigurationError
from app.main import create_app


def setting_overrides(**overrides: object) -> dict[str, object]:
    """Return complete safe settings with selected overrides."""
    values: dict[str, object] = {
        "APP_ENV": "development",
        "DATABASE_URL": "postgresql://local-user:local-placeholder@localhost:5432/ehs_test",
        "DIRECTORIST_BASE_URL": "https://ehsmall.com",
        "DIRECTORIST_API_VERSION": "v1",
        "DIRECTORIST_REQUEST_TIMEOUT_SECONDS": 10,
        "DIRECTORIST_MAX_PAGES": 100,
        "DIRECTORIST_PAGE_SIZE": 20,
        "LOG_LEVEL": "INFO",
    }
    values.update(overrides)
    return values


def validation_error(**overrides: object) -> SettingsConfigurationError:
    """Create and return an expected settings validation error."""
    with pytest.raises(SettingsConfigurationError) as caught:
        Settings(**setting_overrides(**overrides))
    return caught.value


def test_development_settings_load_from_safe_placeholders() -> None:
    settings = Settings(**setting_overrides())

    assert settings.app_env is AppEnvironment.DEVELOPMENT
    assert settings.database_url.get_secret_value().endswith("/ehs_test")
    assert settings.directorist_base_url == "https://ehsmall.com"


def test_test_settings_load() -> None:
    settings = Settings(
        **setting_overrides(
            APP_ENV="test",
            DIRECTORIST_BASE_URL="http://directorist.test",
        )
    )

    assert settings.app_env is AppEnvironment.TEST


def test_invalid_app_environment_is_rejected() -> None:
    validation_error(APP_ENV="preview")


def test_production_rejects_localhost_database() -> None:
    validation_error(APP_ENV="production")


def test_non_test_directorist_url_rejects_http() -> None:
    validation_error(DIRECTORIST_BASE_URL="http://ehsmall.com")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DIRECTORIST_REQUEST_TIMEOUT_SECONDS", 0),
        ("DIRECTORIST_REQUEST_TIMEOUT_SECONDS", 61),
        ("DIRECTORIST_MAX_PAGES", 0),
        ("DIRECTORIST_MAX_PAGES", 1001),
        ("DIRECTORIST_PAGE_SIZE", 0),
        ("DIRECTORIST_PAGE_SIZE", 101),
    ],
)
def test_directorist_numeric_bounds(name: str, value: int) -> None:
    validation_error(**{name: value})


def test_validation_error_does_not_expose_database_password() -> None:
    password = "must-not-appear-in-errors"
    error = validation_error(
        APP_ENV="production",
        DATABASE_URL=f"postgresql://ehs:{password}@localhost:5432/ehs",
    )

    assert password not in str(error)
    assert password not in repr(error)


def test_minimal_application_starts() -> None:
    app = create_app()

    assert app.title == "EHS Mall API"
    assert app.version == "0.1.0"


def test_root_response_is_controlled_and_secret_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "response-secret-sentinel"
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql://ehs:{secret}@localhost:5432/ehs",
    )

    async def request_root() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/")

    response = asyncio.run(request_root())

    assert response.status_code == 200
    assert response.json() == {
        "name": "EHS Mall API",
        "version": "0.1.0",
        "status": "foundation-ready",
    }
    assert secret not in response.text
