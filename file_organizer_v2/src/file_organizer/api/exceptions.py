"""Exception handlers for the API layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger


@dataclass
class ApiError(Exception):
    """Structured API error for consistent responses."""

    status_code: int
    error: str
    message: str
    details: Optional[Any] = None

    def __post_init__(self) -> None:
        summary = f"{self.status_code} {self.error}: {self.message}"
        super().__init__(summary)


def setup_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers on the app."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
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
        logger.warning("API error on {}: {}", request.url.path, exc.error)
        payload: dict[str, Any] = {
            "error": exc.error,
            "message": exc.message,
        }
        if exc.details is not None:
            payload["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception("Unhandled error on {}", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "Unexpected server error.",
            },
        )
