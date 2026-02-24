"""Resource manager for parallel file processing.

This module provides thread-safe resource tracking and allocation to
prevent the file processing system from exceeding CPU, memory, IO, or
GPU limits. Resources are acquired before processing begins and released
when complete.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from file_organizer._compat import StrEnum


class ResourceType(StrEnum):
    """Types of system resources that can be managed."""

    CPU = "cpu"
    MEMORY = "memory"
    IO = "io"
    GPU = "gpu"


@dataclass
class ResourceConfig:
    """Configuration for resource limits.

    Attributes:
        max_cpu_percent: Maximum aggregate CPU usage allowed (0-100+).
            Values above 100 allow multi-core saturation.
        max_memory_mb: Maximum memory in megabytes that may be allocated.
        max_io_operations: Maximum concurrent IO operations permitted.
        max_gpu_percent: Maximum GPU usage allowed (0-100). Defaults to 0
            meaning GPU resources are not managed.
    """

    max_cpu_percent: float = 80.0
    max_memory_mb: int = 1024
    max_io_operations: int = 10
    max_gpu_percent: float = 0.0

    def __post_init__(self) -> None:
        """Validate configuration values after initialization."""
        if self.max_cpu_percent <= 0:
            raise ValueError(f"max_cpu_percent must be > 0, got {self.max_cpu_percent}")
        if self.max_memory_mb <= 0:
            raise ValueError(f"max_memory_mb must be > 0, got {self.max_memory_mb}")
        if self.max_io_operations <= 0:
            raise ValueError(f"max_io_operations must be > 0, got {self.max_io_operations}")
        if self.max_gpu_percent < 0:
            raise ValueError(f"max_gpu_percent must be >= 0, got {self.max_gpu_percent}")


class ResourceManager:
    """Thread-safe resource allocation manager.

    Tracks resource usage across resource types and provides acquire/release
    semantics. ``acquire`` checks whether sufficient resources are available
    and atomically reserves them; ``release`` returns resources to the pool.
    """

    def __init__(self, config: ResourceConfig) -> None:
        """Set up resource limits from the given configuration."""
        self._config = config
        self._lock = threading.Lock()
        self._limits: dict[str, float] = {
            ResourceType.CPU: config.max_cpu_percent,
            ResourceType.MEMORY: float(config.max_memory_mb),
            ResourceType.IO: float(config.max_io_operations),
            ResourceType.GPU: config.max_gpu_percent,
        }
        self._used: dict[str, float] = {
            ResourceType.CPU: 0.0,
            ResourceType.MEMORY: 0.0,
            ResourceType.IO: 0.0,
            ResourceType.GPU: 0.0,
        }

    @property
    def config(self) -> ResourceConfig:
        """Return the current resource configuration."""
        return self._config

    def acquire(self, resource_type: str, amount: float) -> bool:
        """Try to acquire a resource allocation.

        Args:
            resource_type: The type of resource to acquire (use
                :class:`ResourceType` values).
            amount: The amount of the resource to acquire.

        Returns:
            ``True`` if the resource was successfully acquired, ``False``
            if insufficient resources are available.

        Raises:
            ValueError: If *amount* is negative or *resource_type* is unknown.
        """
        if amount < 0:
            raise ValueError(f"amount must be >= 0, got {amount}")

        with self._lock:
            if resource_type not in self._limits:
                raise ValueError(f"Unknown resource type: {resource_type}")

            available = self._limits[resource_type] - self._used[resource_type]
            if amount > available:
                return False

            self._used[resource_type] += amount
            return True

    def release(self, resource_type: str, amount: float) -> None:
        """Release a previously acquired resource allocation.

        The used amount is clamped to zero to prevent underflow in case
        of mismatched acquire/release calls.

        Args:
            resource_type: The type of resource to release.
            amount: The amount of the resource to release.

        Raises:
            ValueError: If *amount* is negative or *resource_type* is unknown.
        """
        if amount < 0:
            raise ValueError(f"amount must be >= 0, got {amount}")

        with self._lock:
            if resource_type not in self._used:
                raise ValueError(f"Unknown resource type: {resource_type}")

            self._used[resource_type] = max(0.0, self._used[resource_type] - amount)

    def get_available(self, resource_type: str) -> float:
        """Return the amount of a resource currently available.

        Args:
            resource_type: The type of resource to query.

        Returns:
            The amount of the resource that is currently free.

        Raises:
            ValueError: If *resource_type* is unknown.
        """
        with self._lock:
            if resource_type not in self._limits:
                raise ValueError(f"Unknown resource type: {resource_type}")
            return self._limits[resource_type] - self._used[resource_type]

    def get_used(self, resource_type: str) -> float:
        """Return the amount of a resource currently in use.

        Args:
            resource_type: The type of resource to query.

        Returns:
            The amount of the resource currently allocated.

        Raises:
            ValueError: If *resource_type* is unknown.
        """
        with self._lock:
            if resource_type not in self._used:
                raise ValueError(f"Unknown resource type: {resource_type}")
            return self._used[resource_type]

    def get_utilization(self, resource_type: str) -> float:
        """Return the utilization ratio of a resource (0.0 to 1.0).

        Args:
            resource_type: The type of resource to query.

        Returns:
            Utilization as a float between 0.0 (idle) and 1.0 (fully used).
            Returns 0.0 if the resource limit is zero.

        Raises:
            ValueError: If *resource_type* is unknown.
        """
        with self._lock:
            if resource_type not in self._limits:
                raise ValueError(f"Unknown resource type: {resource_type}")
            limit = self._limits[resource_type]
            if limit == 0.0:
                return 0.0
            return self._used[resource_type] / limit

    def reset(self) -> None:
        """Release all resources, resetting usage to zero."""
        with self._lock:
            for key in self._used:
                self._used[key] = 0.0
