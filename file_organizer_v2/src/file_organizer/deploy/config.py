"""Deployment configuration for File Organizer v2.

Loads configuration from environment variables with sensible defaults
for different deployment environments (dev, staging, prod).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_ENV_DEFAULTS: dict[str, dict[str, str]] = {
    "dev": {
        "log_level": "DEBUG",
        "max_workers": "2",
        "redis_url": "redis://localhost:6379/0",
    },
    "staging": {
        "log_level": "INFO",
        "max_workers": "4",
        "redis_url": "redis://redis:6379/0",
    },
    "prod": {
        "log_level": "WARNING",
        "max_workers": "8",
        "redis_url": "redis://redis:6379/0",
    },
}

VALID_ENVIRONMENTS = frozenset({"dev", "staging", "prod"})
VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


@dataclass
class DeploymentConfig:
    """Configuration for a File Organizer deployment.

    All fields can be loaded from environment variables. If not set,
    defaults are determined by the ``environment`` setting.

    Attributes:
        environment: Deployment environment (dev, staging, prod).
        redis_url: Redis connection URL for the event/task system.
        data_directory: Path to the persistent data directory.
        log_level: Python logging level string.
        max_workers: Maximum number of concurrent worker processes.
        host: Host to bind the web server to.
        port: Port to bind the web server to.
    """

    environment: str = "dev"
    redis_url: str = "redis://localhost:6379/0"
    data_directory: Path = field(default_factory=lambda: Path("/data"))
    log_level: str = "DEBUG"
    max_workers: int = 2
    host: str = "0.0.0.0"
    port: int = 8000

    def __post_init__(self) -> None:
        """Validate configuration values after initialization."""
        if self.environment not in VALID_ENVIRONMENTS:
            raise ValueError(
                f"Invalid environment: {self.environment!r}. "
                f"Must be one of: {', '.join(sorted(VALID_ENVIRONMENTS))}"
            )
        if self.log_level.upper() not in VALID_LOG_LEVELS:
            raise ValueError(
                f"Invalid log_level: {self.log_level!r}. "
                f"Must be one of: {', '.join(sorted(VALID_LOG_LEVELS))}"
            )
        # Normalize log_level to uppercase
        self.log_level = self.log_level.upper()

        if self.max_workers < 1:
            raise ValueError(f"max_workers must be at least 1, got {self.max_workers}")
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"port must be between 1 and 65535, got {self.port}")
        # Ensure data_directory is a Path
        if isinstance(self.data_directory, str):
            self.data_directory = Path(self.data_directory)

    @classmethod
    def from_env(cls) -> DeploymentConfig:
        """Create a DeploymentConfig from environment variables.

        Reads the following environment variables:

        - ``FO_ENVIRONMENT``: Deployment environment (default: ``dev``)
        - ``FO_REDIS_URL``: Redis connection URL
        - ``FO_DATA_DIR``: Persistent data directory path
        - ``FO_LOG_LEVEL``: Logging level
        - ``FO_MAX_WORKERS``: Maximum worker processes
        - ``FO_HOST``: Server bind host
        - ``FO_PORT``: Server bind port

        Returns:
            A new DeploymentConfig populated from the environment.
        """
        environment = os.environ.get("FO_ENVIRONMENT", "dev").lower()

        # Get environment-specific defaults
        env_defaults = _ENV_DEFAULTS.get(environment, _ENV_DEFAULTS["dev"])

        redis_url = os.environ.get("FO_REDIS_URL", env_defaults["redis_url"])
        data_directory = Path(os.environ.get("FO_DATA_DIR", "/data"))
        log_level = os.environ.get("FO_LOG_LEVEL", env_defaults["log_level"])
        max_workers = int(os.environ.get("FO_MAX_WORKERS", env_defaults["max_workers"]))
        host = os.environ.get("FO_HOST", "0.0.0.0")
        port = int(os.environ.get("FO_PORT", "8000"))

        return cls(
            environment=environment,
            redis_url=redis_url,
            data_directory=data_directory,
            log_level=log_level,
            max_workers=max_workers,
            host=host,
            port=port,
        )

    @property
    def is_production(self) -> bool:
        """Return True if this is a production deployment."""
        return self.environment == "prod"

    @property
    def is_development(self) -> bool:
        """Return True if this is a development deployment."""
        return self.environment == "dev"

    @property
    def redis_host(self) -> str:
        """Extract the host from the Redis URL.

        Returns:
            The hostname portion of the Redis URL.
        """
        # Simple parsing: redis://host:port/db
        url = self.redis_url
        if "://" in url:
            url = url.split("://", 1)[1]
        if "/" in url:
            url = url.split("/", 1)[0]
        if ":" in url:
            url = url.split(":", 1)[0]
        return url

    @property
    def redis_port(self) -> int:
        """Extract the port from the Redis URL.

        Returns:
            The port number from the Redis URL, defaulting to 6379.
        """
        url = self.redis_url
        if "://" in url:
            url = url.split("://", 1)[1]
        if "/" in url:
            url = url.split("/", 1)[0]
        if ":" in url:
            port_str = url.split(":", 1)[1]
            return int(port_str)
        return 6379
