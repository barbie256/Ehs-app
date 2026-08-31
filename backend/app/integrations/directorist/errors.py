"""Safe Directorist adapter error taxonomy."""


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


class DirectoristMappingError(DirectoristError):
    code = "mapping_error"
