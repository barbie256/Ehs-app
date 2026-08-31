"""Typed settings with safe environment validation."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Supported deployment environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class SettingsConfigurationError(ValueError):
    """A configuration failure containing no original input values."""


class Settings(BaseSettings):
    """Application settings loaded from environment variables or safe defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        alias_generator=str.upper,
        populate_by_name=True,
    )

    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://ehs_mall_local:replace-with-local-password@127.0.0.1:5432/ehs_mall_dev"
    )
    test_database_url: SecretStr | None = None
    directorist_base_url: str = "https://ehsmall.com"
    directorist_api_version: str = "v1"
    directorist_request_timeout_seconds: Annotated[float, Field(ge=1, le=60)] = 10
    directorist_max_pages: Annotated[int, Field(ge=1, le=1000)] = 100
    directorist_page_size: Annotated[int, Field(ge=1, le=100)] = 20
    log_level: str = "INFO"

    def __init__(self, **values: object) -> None:
        """Validate settings while removing Pydantic's raw input error payload."""
        try:
            super().__init__(**values)  # type: ignore[arg-type]
        except ValidationError as error:
            messages = []
            for detail in error.errors(include_input=False, include_url=False):
                location = ".".join(str(part) for part in detail["loc"])
                messages.append(f"{location}: {detail['msg']}")
            raise SettingsConfigurationError("; ".join(messages)) from None

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        """Protect local and known production database boundaries."""
        database = urlsplit(value.get_secret_value())
        database_host = (database.hostname or "").lower()
        environment = info.data.get("app_env", AppEnvironment.DEVELOPMENT)
        localhost_hosts = {"localhost", "127.0.0.1", "::1"}
        known_production_hosts = {"ehsmall.com", "www.ehsmall.com"}
        if environment is AppEnvironment.PRODUCTION and database_host in localhost_hosts:
            raise ValueError("production DATABASE_URL must not use a local host")
        if (
            environment in {AppEnvironment.DEVELOPMENT, AppEnvironment.TEST}
            and database_host in known_production_hosts
        ):
            raise ValueError("development and test must not use a known production host")
        return value

    @field_validator("directorist_base_url")
    @classmethod
    def validate_directorist_base_url(cls, value: str, info: ValidationInfo) -> str:
        """Enforce a credential-free HTTPS source boundary outside tests."""
        directorist = urlsplit(value)
        environment = info.data.get("app_env", AppEnvironment.DEVELOPMENT)
        if not directorist.hostname or directorist.username or directorist.password:
            raise ValueError("DIRECTORIST_BASE_URL must be an absolute URL without credentials")
        if directorist.path not in {"", "/"} or directorist.query or directorist.fragment:
            raise ValueError("DIRECTORIST_BASE_URL must contain only scheme and host")
        if environment is not AppEnvironment.TEST and directorist.scheme != "https":
            raise ValueError("DIRECTORIST_BASE_URL must use HTTPS outside tests")
        if environment is AppEnvironment.PRODUCTION and directorist.hostname != "ehsmall.com":
            raise ValueError("production Directorist host is not approved")
        return value

    @field_validator("directorist_api_version")
    @classmethod
    def validate_api_version(cls, value: str) -> str:
        """Limit the foundation to the audited Directorist API version."""
        if value != "v1":
            raise ValueError("unsupported Directorist API version")
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Normalize and validate supported logging levels."""
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("unsupported log level")
        return normalized


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance for the application process."""
    return Settings()
