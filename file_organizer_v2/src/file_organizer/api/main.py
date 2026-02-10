"""FastAPI application entrypoint."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from loguru import logger

from file_organizer.api.config import ApiSettings, load_settings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.middleware import setup_middleware
from file_organizer.api.routers import (
    auth_router,
    dedupe_router,
    files_router,
    health_router,
    organize_router,
    realtime_router,
    system_router,
)

_LOGGING_CONFIGURED = False


def configure_logging(settings: ApiSettings) -> None:
    """Configure structured logging to console and file."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    log_dir = Path.home() / ".config" / "file-organizer" / "logs"
    log_file: Optional[Path] = None
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "api.log"
    except OSError as exc:
        print(f"Warning: failed to create log directory {log_dir}: {exc}", file=sys.stderr)

    logger.remove()
    logger.add(sys.stdout, level=settings.log_level, enqueue=True)
    if log_file is not None:
        logger.add(log_file, level=settings.log_level, rotation="10 MB", retention="14 days")

    _LOGGING_CONFIGURED = True


def create_app(settings: Optional[ApiSettings] = None) -> FastAPI:
    """Create the FastAPI application."""
    settings = settings or load_settings()
    configure_logging(settings)

    docs_url = "/docs" if settings.enable_docs else None
    redoc_url = "/redoc" if settings.enable_docs else None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info("Starting API in {} mode", settings.environment)
        yield
        logger.info("Shutting down API")

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="REST API for AI-powered file organization",
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )

    setup_middleware(app, settings)
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(files_router, prefix="/api/v1")
    app.include_router(organize_router, prefix="/api/v1")
    app.include_router(dedupe_router, prefix="/api/v1")
    app.include_router(realtime_router, prefix="/api/v1")
    app.include_router(system_router, prefix="/api/v1")

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": settings.version,
        }

    return app


app = create_app()
