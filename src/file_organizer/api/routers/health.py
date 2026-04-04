"""Health check endpoints.

The /health route is the authoritative readiness probe for the desktop launcher.
The pywebview launcher polls this endpoint to determine when the Python backend is ready.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Response
from loguru import logger

router = APIRouter(tags=["health"])

# Startup time used to compute uptime in health responses.
# Use monotonic time to avoid issues with system clock adjustments (NTP sync).
# Defaults to module-import time; call ``reset_startup_time()`` from the app
# lifespan/startup event so that recreated app instances report accurate uptime.
_startup_time: float = time.monotonic()


def reset_startup_time() -> None:
    """Reset startup time — call from app lifespan/startup event."""
    global _startup_time
    _startup_time = time.monotonic()


@router.get("/health")
async def health(response: Response) -> dict[str, object]:
    """Return rich health status for the API and desktop launcher readiness probe.

    Response shape::

        {
            "status":    "ok" | "degraded" | "unknown" | "error",
            "readiness": "ready" | "starting" | "unhealthy",
            "version":   "<semver string>",
            "provider":  "ollama" | "openai" | "llama_cpp" | "mlx",
            "ollama":    true | false,
            "uptime":    <float seconds since startup>
        }

    The ``readiness`` field maps directly from ``status``:

    * ``"ok"``       -> ``"ready"``
    * ``"unknown"``  -> ``"ready"``  (provider not probed, e.g. OpenAI/llama_cpp/mlx endpoints)
    * ``"degraded"`` -> ``"starting"``
    * ``"error"``    -> ``"unhealthy"``

    HTTP status codes:

    * ``200`` – status is "ok" or "unknown"
    * ``207`` – status is "degraded" (backend running but Ollama unreachable)
    * ``503`` – status is "error"
    """
    # Lazy import to avoid circular dependency:
    # service_facade → api.routers → health → service_facade
    from file_organizer.api.service_facade import ServiceFacade

    facade = ServiceFacade()
    try:
        payload = await facade.health_check()
    except Exception as exc:
        logger.warning("health_check failed: {}", exc, exc_info=True)
        payload = {}

    # Use the status derived by the facade rather than re-deriving it here.
    # The facade returns "ok" / "degraded" / "unknown"; we add "error" for
    # total failure.  "unknown" means the provider has not been probed (e.g.
    # OpenAI-compatible endpoint) — treat as ready so the desktop launcher starts.
    status: str = str(payload.get("status", "error")) if payload else "error"

    _READINESS_MAP: dict[str, str] = {
        "ok": "ready",
        "unknown": "ready",  # provider not probed — optimistically ready
        "degraded": "starting",
        "error": "unhealthy",
    }

    result: dict[str, object] = {
        "status": status,
        "readiness": _READINESS_MAP.get(status, "unhealthy"),
        "version": payload.get("version", ""),
        "provider": payload.get("provider", "ollama"),
        "ollama": bool(payload.get("ollama", False)),
        "uptime": time.monotonic() - _startup_time,
    }

    if status == "degraded":
        response.status_code = 207
    elif status == "error":
        response.status_code = 503
    # "ok" → default 200

    return result
