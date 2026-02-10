"""Exception handlers for the API layer."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger


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
                "details": [
                    {"loc": err.get("loc"), "msg": err.get("msg")}
                    for err in exc.errors()
                ],
            },
        )

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
