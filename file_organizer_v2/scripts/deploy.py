"""Deployment automation for File Organizer v2 Docker images.

Provides functions for building, pushing, validating, and rolling back
Docker image deployments.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class DeployConfig:
    """Configuration for a deployment operation.

    Attributes:
        registry: Docker registry URL (e.g., ``docker.io/myuser``).
        image_name: Name of the Docker image.
        tag: Tag for the Docker image (e.g., ``v2.0.0``, ``latest``).
        env_file: Optional path to an environment file for the container.
    """

    registry: str
    image_name: str
    tag: str
    env_file: str | None = None

    @property
    def full_image_name(self) -> str:
        """Return the fully qualified image name with registry and tag."""
        return f"{self.registry}/{self.image_name}:{self.tag}"


@dataclass
class HealthCheckResult:
    """Result of a deployment health check.

    Attributes:
        healthy: Whether the deployment is healthy.
        status_code: HTTP status code from the health endpoint.
        response_time_ms: Time taken to get the health response, in milliseconds.
        details: Optional dictionary with additional health details.
    """

    healthy: bool
    status_code: int
    response_time_ms: float
    details: dict[str, object] | None = None


def build_image(tag: str, dockerfile: str = "Dockerfile") -> bool:
    """Build a Docker image from the specified Dockerfile.

    Args:
        tag: Tag to apply to the built image.
        dockerfile: Path to the Dockerfile (default: ``Dockerfile``).

    Returns:
        True if the build succeeded, False otherwise.
    """
    cmd = [
        "docker",
        "build",
        "-f",
        dockerfile,
        "-t",
        tag,
        ".",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def push_image(tag: str, registry: str) -> bool:
    """Push a Docker image to a registry.

    The image is first tagged with the registry prefix, then pushed.

    Args:
        tag: Local image tag to push.
        registry: Target registry URL.

    Returns:
        True if the push succeeded, False otherwise.
    """
    remote_tag = f"{registry}/{tag}"

    # Tag the image for the registry
    tag_cmd = ["docker", "tag", tag, remote_tag]
    try:
        tag_result = subprocess.run(
            tag_cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if tag_result.returncode != 0:
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False

    # Push the tagged image
    push_cmd = ["docker", "push", remote_tag]
    try:
        push_result = subprocess.run(
            push_cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return push_result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def validate_deployment(url: str) -> HealthCheckResult:
    """Validate a deployment by checking its health endpoint.

    Sends an HTTP GET request to the specified health check URL
    and returns the result.

    Args:
        url: Full URL of the health check endpoint
            (e.g., ``http://localhost:8000/health``).

    Returns:
        A HealthCheckResult indicating the deployment health.
    """
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=10) as response:
            elapsed_ms = (time.monotonic() - start) * 1000
            status_code = response.status
            body = response.read().decode("utf-8")
            try:
                details = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                details = {"raw": body}

            healthy = status_code == 200
            if isinstance(details, dict) and "status" in details:
                healthy = details["status"] == "healthy"

            return HealthCheckResult(
                healthy=healthy,
                status_code=status_code,
                response_time_ms=round(elapsed_ms, 2),
                details=details,
            )
    except urllib.error.HTTPError as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        return HealthCheckResult(
            healthy=False,
            status_code=exc.code,
            response_time_ms=round(elapsed_ms, 2),
            details={"error": str(exc)},
        )
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        return HealthCheckResult(
            healthy=False,
            status_code=0,
            response_time_ms=round(elapsed_ms, 2),
            details={"error": str(exc)},
        )


def rollback(previous_tag: str) -> bool:
    """Roll back to a previous Docker image tag.

    Stops the current container, removes it, and starts the previous
    version using docker-compose.

    Args:
        previous_tag: The image tag to roll back to.

    Returns:
        True if the rollback succeeded, False otherwise.
    """
    # Stop the current deployment
    stop_cmd = ["docker-compose", "down"]
    try:
        stop_result = subprocess.run(
            stop_cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if stop_result.returncode != 0:
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False

    # Start with the previous tag
    env = {"FILE_ORGANIZER_TAG": previous_tag}
    up_cmd = ["docker-compose", "up", "-d"]
    try:
        merged_env = {**os.environ, **env}
        up_result = subprocess.run(
            up_cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=merged_env,
        )
        return up_result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
