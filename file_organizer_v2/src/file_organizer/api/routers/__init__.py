"""API routers package."""
from file_organizer.api.routers.auth import router as auth_router
from file_organizer.api.routers.dedupe import router as dedupe_router
from file_organizer.api.routers.files import router as files_router
from file_organizer.api.routers.health import router as health_router
from file_organizer.api.routers.organize import router as organize_router
from file_organizer.api.routers.realtime import router as realtime_router
from file_organizer.api.routers.system import router as system_router

__all__ = [
    "auth_router",
    "health_router",
    "files_router",
    "organize_router",
    "dedupe_router",
    "realtime_router",
    "system_router",
]
