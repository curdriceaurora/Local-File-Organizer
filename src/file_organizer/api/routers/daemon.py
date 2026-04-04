"""Daemon control endpoints.

Provides REST API endpoints for starting, stopping, and toggling the
background daemon service. Called by the desktop context menu.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/daemon", tags=["daemon"])


@router.post("/toggle")
async def toggle_daemon() -> dict[str, Any]:
    """Toggle the daemon between running and stopped states.

    Returns the new daemon state after toggling.  If the status check
    itself fails, the error is propagated so callers know the toggle
    could not be performed.
    """
    from file_organizer.api.service_facade import ServiceFacade

    facade = ServiceFacade()
    status = await facade.get_daemon_status()

    if not status.get("success"):
        return {
            "success": False,
            "error": status.get("error", "Unable to determine daemon status"),
        }

    is_running = status.get("data", {}).get("running", False)

    if is_running:
        result = await facade.stop_daemon()
    else:
        result = await facade.start_daemon()

    return result


@router.post("/start")
async def start_daemon() -> dict[str, Any]:
    """Start the background daemon service.

    Returns the current status if the daemon is already running.
    """
    from file_organizer.api.service_facade import ServiceFacade

    facade = ServiceFacade()

    # Check if already running to provide a clear response
    status = await facade.get_daemon_status()
    if status.get("success") and status.get("data", {}).get("running"):
        return {"success": True, "data": {"started": True, "already_running": True}}

    return await facade.start_daemon()


@router.post("/stop")
async def stop_daemon() -> dict[str, Any]:
    """Stop the background daemon service.

    Returns the current status if the daemon is already stopped.
    """
    from file_organizer.api.service_facade import ServiceFacade

    facade = ServiceFacade()

    # Check if already stopped to provide a clear response
    status = await facade.get_daemon_status()
    if status.get("success") and not status.get("data", {}).get("running"):
        return {"success": True, "data": {"stopped": True, "already_stopped": True}}

    return await facade.stop_daemon()


@router.get("/status")
async def daemon_status() -> dict[str, Any]:
    """Get the current daemon status."""
    from file_organizer.api.service_facade import ServiceFacade

    facade = ServiceFacade()
    return await facade.get_daemon_status()
