"""FastAPI application entrypoint."""

from __future__ import annotations

import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger

from file_organizer.api.config import ApiSettings, load_settings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.middleware import setup_middleware
from file_organizer.api.routers import (
    analyze_router,
    auth_router,
    config_router,
    daemon_router,
    dedupe_router,
    files_router,
    health_router,
    integrations_router,
    marketplace_router,
    organize_router,
    realtime_router,
    search_router,
    system_router,
)
from file_organizer.api.routers.integrations import (
    build_browser_extension_manager,
    build_integration_manager,
)
from file_organizer.plugins.api.endpoints import router as plugin_api_router
from file_organizer.web import STATIC_DIR
from file_organizer.web import router as web_router

_LOGGING_CONFIGURED = False
_app: FastAPI | None = None
_app_lock = threading.Lock()


def configure_logging(settings: ApiSettings) -> None:
    """Configure structured logging to console and file."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    from file_organizer.config.path_manager import get_state_dir

    log_dir = get_state_dir() / "logs"
    log_file: Path | None = None
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


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Create the FastAPI application."""
    settings = settings or load_settings()
    configure_logging(settings)

    docs_url = "/docs" if settings.enable_docs else None
    redoc_url = "/redoc" if settings.enable_docs else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    else:
        logger.warning("Static assets directory not found at {}", STATIC_DIR)

    setup_middleware(app, settings)
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.integration_manager = build_integration_manager(settings)
    app.state.browser_extension_manager = build_browser_extension_manager(settings)

    app.include_router(web_router, prefix="/ui")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(files_router, prefix="/api/v1")
    app.include_router(organize_router, prefix="/api/v1")
    app.include_router(analyze_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(config_router, prefix="/api/v1")
    app.include_router(dedupe_router, prefix="/api/v1")
    app.include_router(realtime_router, prefix="/api/v1")
    app.include_router(system_router, prefix="/api/v1")
    app.include_router(integrations_router, prefix="/api/v1")
    app.include_router(marketplace_router, prefix="/api/v1")
    app.include_router(plugin_api_router, prefix="/api/v1")
    if daemon_router is not None:
        app.include_router(daemon_router, prefix="/api/v1")

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": settings.version,
        }

    return app


def get_app() -> FastAPI:
    """Get or create the FastAPI application instance (thread-safe).

    This function implements lazy initialization with thread safety to avoid:
    - Import-time side effects (creating .config directories)
    - Multiple app instances due to race conditions in multi-threaded contexts
    - Test isolation issues in concurrent test environments

    The first call to this function will trigger app creation via create_app().
    Subsequent calls return the cached instance. Thread-safe via lock protection.

    Intended for: Test infrastructure, application startup hooks, ASGI servers
    with multiple worker threads

    Returns:
        The initialized and cached FastAPI application instance.
    """
    global _app

    # Quick check without lock for performance (reading stale value is acceptable)
    if _app is not None:
        return _app

    # Double-checked locking pattern for thread-safe lazy initialization
    with _app_lock:
        # Re-check after acquiring lock (another thread may have initialized)
        if _app is None:
            _app = create_app()

        return _app
