"""Exception handlers for the API layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

from file_organizer.core.errors import DomainError, DomainErrorCode

_DOMAIN_HTTP_STATUS = {
    DomainErrorCode.INVALID_REQUEST: 400,
    DomainErrorCode.NOT_FOUND: 404,
    DomainErrorCode.CONFLICT: 409,
    DomainErrorCode.OPTIONAL_FEATURE_UNAVAILABLE: 503,
    DomainErrorCode.PLAN_MISMATCH: 409,
    DomainErrorCode.INVALID_JOB_TRANSITION: 409,
    DomainErrorCode.STALE_JOB_REVISION: 409,
    DomainErrorCode.EXECUTION_FAILED: 500,
    DomainErrorCode.RECOVERY_REQUIRED: 409,
    DomainErrorCode.CANCELLED: 409,
}


@dataclass
class ApiError(Exception):
    """Structured API error for consistent responses."""

    status_code: int
    error: str
    message: str
    details: Any | None = None

    def __post_init__(self) -> None:
        """Initialize ApiError and set exception message from fields."""
        summary = f"{self.status_code} {self.error}: {self.message}"
        super().__init__(summary)


def setup_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers on the app."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Convert a Pydantic ValidationError into a 422 JSON response."""
        logger.warning("Validation error on {}: {}", request.url.path, exc)
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "Invalid request payload.",
                "details": [{"loc": err.get("loc"), "msg": err.get("msg")} for err in exc.errors()],
            },
        )

    @app.exception_handler(ApiError)
    async def api_error_handler(
        request: Request,
        exc: ApiError,
    ) -> JSONResponse:
        """Convert an ApiError into a structured JSON response with the error's status code."""
        logger.warning("API error on {}: {}", request.url.path, exc.error)
        payload: dict[str, Any] = {
            "error": exc.error,
            "message": exc.message,
        }
        if exc.details is not None:
            payload["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(DomainError)
    async def domain_error_handler(
        request: Request,
        exc: DomainError,
    ) -> JSONResponse:
        """Translate a stable domain error without changing its meaning."""
        logger.warning("Domain error on {}: {}", request.url.path, exc.code.value)
        return JSONResponse(
            status_code=_DOMAIN_HTTP_STATUS[exc.code],
            content={"error": exc.code.value, **exc.to_dict()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Fallback handler that logs unexpected errors and returns a 500."""
        logger.exception("Unhandled error on {}", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "Unexpected server error.",
            },
        )
