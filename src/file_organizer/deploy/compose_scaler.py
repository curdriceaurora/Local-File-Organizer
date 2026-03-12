"""Docker Compose service scaling wrapper.

Provides a Python interface around ``docker-compose`` scale commands
for programmatic control of service replica counts in containerised
deployments.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger(__name__)


class ComposeScaler:
    """Scale Docker Compose services programmatically.

    Wraps the ``docker-compose`` CLI to adjust service replica counts
    and query current state.  All subprocess calls are isolated into
    private methods so they can be easily mocked in tests.

    Args:
        compose_file: Path to the docker-compose YAML file.
            Defaults to ``"docker-compose.yml"``.
        project_name: Optional Compose project name override.

    Example:
        >>> scaler = ComposeScaler(compose_file="docker-compose.yml")
        >>> scaler.scale_service("file-organizer", 3)
        True
        >>> scaler.get_service_count("file-organizer")
        3
    """

    def __init__(
        self,
        compose_file: str = "docker-compose.yml",
        project_name: str | None = None,
    ) -> None:
        """Set up the Compose scaler for the given compose file and project."""
        self._compose_file = compose_file
        self._project_name = project_name

    def scale_service(self, service: str, replicas: int) -> bool:
        """Scale a Compose service to the given replica count.

        Args:
            service: Name of the service as defined in the Compose file.
            replicas: Desired number of running replicas (must be >= 0).

        Returns:
            True if the scaling command succeeded, False otherwise.

        Raises:
            ValueError: If *replicas* is negative.
        """
        if replicas < 0:
            raise ValueError(f"replicas must be >= 0, got {replicas}")

        cmd = self._build_command(
            "up", "-d", "--scale", f"{service}={replicas}", "--no-recreate", service
        )

        logger.info("Scaling service '%s' to %d replicas", service, replicas)
        return self._run_command(cmd)

    def get_service_count(self, service: str) -> int:
        """Return the number of running containers for *service*.

        Args:
            service: Name of the service as defined in the Compose file.

        Returns:
            Number of running containers for the service, or 0 if the
            query fails.
        """
        cmd = self._build_command("ps", "--format", "json", service)
        output = self._run_command_output(cmd)

        if output is None:
            return 0

        # Each running container produces one JSON line.
        lines = [line.strip() for line in output.strip().splitlines() if line.strip()]
        return len(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_command(self, *args: str) -> list[str]:
        """Build a ``docker-compose`` command list."""
        cmd: list[str] = ["docker-compose", "-f", self._compose_file]
        if self._project_name:
            cmd.extend(["-p", self._project_name])
        cmd.extend(args)
        return cmd

    def _run_command(self, cmd: list[str]) -> bool:
        """Execute a command and return True on success.

        This method is the single point of subprocess execution for
        mutation operations, making it straightforward to mock.
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                logger.error(
                    "Command failed (rc=%d): %s\nstderr: %s",
                    result.returncode,
                    " ".join(cmd),
                    result.stderr,
                )
                return False
            return True
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
            logger.error("Command execution error: %s", exc, exc_info=True)
            return False

    def _run_command_output(self, cmd: list[str]) -> str | None:
        """Execute a command and return its stdout, or None on failure.

        This method is the single point of subprocess execution for
        query operations, making it straightforward to mock.
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode != 0:
                logger.error(
                    "Command failed (rc=%d): %s\nstderr: %s",
                    result.returncode,
                    " ".join(cmd),
                    result.stderr,
                )
                return None
            return result.stdout
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
            logger.error("Command execution error: %s", exc, exc_info=True)
            return None
