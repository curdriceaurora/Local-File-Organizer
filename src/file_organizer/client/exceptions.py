"""Exception classes for the File Organizer API client."""

from __future__ import annotations

from typing import Any


class ClientError(Exception):
    """Base client error raised for non-success HTTP responses.

    Attributes:
        status_code: The HTTP status code from the server response.
        detail: Optional detail message extracted from the response body.
        error_code: Stable machine-readable server error code.
        details: Optional structured server error evidence.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 0,
        detail: str = "",
        *,
        error_code: str = "",
        details: Any = None,
    ) -> None:
        """Initialize the client error with message, status code, and detail."""
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code
        self.details = details


class AuthenticationError(ClientError):
    """Raised for HTTP 401 Unauthorized or 403 Forbidden responses."""


class NotFoundError(ClientError):
    """Raised for HTTP 404 Not Found responses."""


class ServerError(ClientError):
    """Raised for HTTP 5xx server error responses."""


class ValidationError(ClientError):
    """Raised for HTTP 422 Unprocessable Entity responses."""
