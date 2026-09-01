"""Safe Directorist adapter error taxonomy."""

from dataclasses import dataclass
from typing import Literal

PaginationReason = Literal[
    "missing_total",
    "invalid_total",
    "missing_total_pages",
    "invalid_total_pages",
    "negative_metadata",
    "zero_pages_with_items",
    "page_exceeds_total_pages",
    "total_below_collection_count",
    "total_pages_exceeds_configured_bound",
    "pagination_validation",
]
PAGINATION_REASONS: tuple[PaginationReason, ...] = (
    "missing_total",
    "invalid_total",
    "missing_total_pages",
    "invalid_total_pages",
    "negative_metadata",
    "zero_pages_with_items",
    "page_exceeds_total_pages",
    "total_below_collection_count",
    "total_pages_exceeds_configured_bound",
    "pagination_validation",
)


@dataclass(frozen=True)
class PaginationDiagnostic:
    """Bounded pagination state containing no raw header or response values."""

    total_header_present: bool
    total_header_integer_valid: bool
    total_pages_header_present: bool
    total_pages_header_integer_valid: bool
    reported_total: int | None
    reported_total_pages: int | None
    requested_page: int
    returned_collection_count: int
    configured_max_pages: int


class DirectoristError(RuntimeError):
    code = "directorist_error"

    def __init__(self, message: str = "Directorist request failed") -> None:
        self.safe_message = message
        super().__init__(message)


class DirectoristUnavailableError(DirectoristError):
    code = "unavailable"


class DirectoristTimeoutError(DirectoristError):
    code = "timeout"


class DirectoristRateLimitError(DirectoristError):
    code = "rate_limited"


class DirectoristHTTPError(DirectoristError):
    code = "http_error"


class DirectoristRedirectError(DirectoristError):
    code = "redirect_rejected"


class DirectoristContentTypeError(DirectoristError):
    code = "invalid_content_type"


class DirectoristResponseTooLargeError(DirectoristError):
    code = "response_too_large"


class DirectoristJSONError(DirectoristError):
    code = "invalid_json"


class DirectoristResponseFormatError(DirectoristError):
    code = "invalid_response_shape"


class DirectoristSchemaError(DirectoristError):
    code = "schema_error"


class DirectoristPaginationError(DirectoristError):
    code = "pagination_error"

    def __init__(
        self,
        message: str = "Directorist pagination validation failed",
        *,
        reason: PaginationReason = "pagination_validation",
        diagnostic: PaginationDiagnostic | None = None,
    ) -> None:
        self.reason: PaginationReason = (
            reason if reason in PAGINATION_REASONS else "pagination_validation"
        )
        self.diagnostic = diagnostic
        super().__init__(message)


class DirectoristMappingError(DirectoristError):
    code = "mapping_error"
