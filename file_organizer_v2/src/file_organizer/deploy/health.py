"""Health check endpoint for File Organizer v2 deployments.

Provides health check functionality that reports on the status of
the application and its dependencies (Redis, disk space, model availability).
"""

from __future__ import annotations

import shutil
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path

from file_organizer.deploy.config import DeploymentConfig
from file_organizer.version import __version__


@dataclass
class ComponentStatus:
    """Status of an individual component.

    Attributes:
        name: Human-readable component name.
        healthy: Whether the component is functioning correctly.
        message: Optional status message or error description.
        response_time_ms: Time taken to check the component, in milliseconds.
    """

    name: str
    healthy: bool
    message: str = ""
    response_time_ms: float = 0.0


@dataclass
class HealthEndpoint:
    """Health check endpoint for monitoring File Organizer deployments.

    Checks the health of the application and its dependencies including
    Redis connectivity, disk space availability, and model service
    availability.

    Attributes:
        config: The deployment configuration to use for health checks.
        start_time: Unix timestamp of when the application started.
        min_disk_space_mb: Minimum required free disk space in megabytes.
        model_host: Hostname of the Ollama model service.
        model_port: Port of the Ollama model service.
    """

    config: DeploymentConfig
    start_time: float = field(default_factory=time.time)
    min_disk_space_mb: int = 100
    model_host: str = "localhost"
    model_port: int = 11434

    def get_health(self) -> dict[str, object]:
        """Get comprehensive health status of the application.

        Returns:
            A dictionary containing:
            - ``status``: Overall health status (``"healthy"`` or ``"unhealthy"``).
            - ``version``: Application version string.
            - ``uptime_seconds``: Seconds since the application started.
            - ``environment``: Deployment environment name.
            - ``components``: Dictionary mapping component names to their status.
        """
        components: dict[str, dict[str, object]] = {}

        redis_status = self._check_redis()
        components["redis"] = {
            "healthy": redis_status.healthy,
            "message": redis_status.message,
            "response_time_ms": redis_status.response_time_ms,
        }

        disk_status = self._check_disk_space()
        components["disk"] = {
            "healthy": disk_status.healthy,
            "message": disk_status.message,
            "response_time_ms": disk_status.response_time_ms,
        }

        model_status = self._check_model_availability()
        components["model"] = {
            "healthy": model_status.healthy,
            "message": model_status.message,
            "response_time_ms": model_status.response_time_ms,
        }

        all_healthy = all(comp["healthy"] for comp in components.values())

        return {
            "status": "healthy" if all_healthy else "unhealthy",
            "version": __version__,
            "uptime_seconds": round(time.time() - self.start_time, 2),
            "environment": self.config.environment,
            "components": components,
        }

    def check_redis(self) -> bool:
        """Check if Redis is reachable.

        Attempts a TCP connection to the Redis host and port extracted
        from the deployment configuration.

        Returns:
            True if Redis is reachable, False otherwise.
        """
        return self._check_redis().healthy

    def _check_redis(self) -> ComponentStatus:
        """Internal Redis health check with detailed status.

        Returns:
            ComponentStatus with Redis connectivity details.
        """
        start = time.monotonic()
        try:
            host = self.config.redis_host
            port = self.config.redis_port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            result = sock.connect_ex((host, port))
            sock.close()
            elapsed_ms = (time.monotonic() - start) * 1000

            if result == 0:
                return ComponentStatus(
                    name="redis",
                    healthy=True,
                    message=f"Connected to {host}:{port}",
                    response_time_ms=round(elapsed_ms, 2),
                )
            else:
                return ComponentStatus(
                    name="redis",
                    healthy=False,
                    message=f"Connection refused at {host}:{port}",
                    response_time_ms=round(elapsed_ms, 2),
                )
        except OSError as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            return ComponentStatus(
                name="redis",
                healthy=False,
                message=f"Connection error: {exc}",
                response_time_ms=round(elapsed_ms, 2),
            )

    def check_disk_space(self) -> bool:
        """Check if sufficient disk space is available.

        Checks the free space on the partition containing the configured
        data directory against the minimum requirement.

        Returns:
            True if free disk space exceeds the minimum threshold.
        """
        return self._check_disk_space().healthy

    def _check_disk_space(self) -> ComponentStatus:
        """Internal disk space check with detailed status.

        Returns:
            ComponentStatus with disk space details.
        """
        start = time.monotonic()
        try:
            data_dir = self.config.data_directory
            # Use parent directory if data_directory doesn't exist yet
            check_path = data_dir if data_dir.exists() else Path("/")
            usage = shutil.disk_usage(str(check_path))
            free_mb = usage.free / (1024 * 1024)
            total_mb = usage.total / (1024 * 1024)
            elapsed_ms = (time.monotonic() - start) * 1000

            healthy = free_mb >= self.min_disk_space_mb
            return ComponentStatus(
                name="disk",
                healthy=healthy,
                message=(
                    f"{free_mb:.0f}MB free of {total_mb:.0f}MB total"
                    if healthy
                    else f"Low disk space: {free_mb:.0f}MB free "
                    f"(minimum: {self.min_disk_space_mb}MB)"
                ),
                response_time_ms=round(elapsed_ms, 2),
            )
        except OSError as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            return ComponentStatus(
                name="disk",
                healthy=False,
                message=f"Disk check error: {exc}",
                response_time_ms=round(elapsed_ms, 2),
            )

    def check_model_availability(self) -> bool:
        """Check if the Ollama model service is reachable.

        Attempts a TCP connection to the configured model host and port.

        Returns:
            True if the model service is reachable, False otherwise.
        """
        return self._check_model_availability().healthy

    def _check_model_availability(self) -> ComponentStatus:
        """Internal model availability check with detailed status.

        Returns:
            ComponentStatus with model service connectivity details.
        """
        start = time.monotonic()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            result = sock.connect_ex((self.model_host, self.model_port))
            sock.close()
            elapsed_ms = (time.monotonic() - start) * 1000

            if result == 0:
                return ComponentStatus(
                    name="model",
                    healthy=True,
                    message=f"Ollama reachable at {self.model_host}:{self.model_port}",
                    response_time_ms=round(elapsed_ms, 2),
                )
            else:
                return ComponentStatus(
                    name="model",
                    healthy=False,
                    message=(f"Ollama not reachable at {self.model_host}:{self.model_port}"),
                    response_time_ms=round(elapsed_ms, 2),
                )
        except OSError as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            return ComponentStatus(
                name="model",
                healthy=False,
                message=f"Model check error: {exc}",
                response_time_ms=round(elapsed_ms, 2),
            )
