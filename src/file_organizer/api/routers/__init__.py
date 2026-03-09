"""API routers package."""

from file_organizer.api.routers.analyze import router as analyze_router
from file_organizer.api.routers.auth import router as auth_router
from file_organizer.api.routers.config import router as config_router
from file_organizer.api.routers.dedupe import router as dedupe_router
from file_organizer.api.routers.files import router as files_router
from file_organizer.api.routers.health import router as health_router
from file_organizer.api.routers.integrations import router as integrations_router
from file_organizer.api.routers.marketplace import router as marketplace_router
from file_organizer.api.routers.organize import router as organize_router
from file_organizer.api.routers.realtime import router as realtime_router
from file_organizer.api.routers.search import router as search_router
from file_organizer.api.routers.system import router as system_router

try:
    from file_organizer.api.routers.daemon import router as daemon_router
except ModuleNotFoundError as exc:
    if "daemon" not in (exc.name or ""):
        raise  # Re-raise if a transitive dependency is missing, not the daemon module
    import warnings

    warnings.warn("daemon router not available; daemon endpoints disabled", stacklevel=1)
    daemon_router = None

__all__ = [
    "analyze_router",
    "auth_router",
    "config_router",
    "daemon_router",
    "health_router",
    "files_router",
    "integrations_router",
    "marketplace_router",
    "organize_router",
    "dedupe_router",
    "realtime_router",
    "search_router",
    "system_router",
]
