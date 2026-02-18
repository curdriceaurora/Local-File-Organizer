"""Health checking for registered services.

Provides a health-check protocol that queries services for their
current status and tracks latency, degradation, and failure
history.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from file_organizer.events.discovery import ServiceDiscovery
from file_organizer.events.service_bus import ServiceBus

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Types
# ------------------------------------------------------------------


class HealthStatus(Enum):
    """Possible health states for a service."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """Health-check result for a single service.

    Attributes:
        name: Service name that was checked.
        status: Resolved health status.
        latency_ms: Round-trip time for the health check in ms.
        last_check: UTC timestamp of this check.
        details: Arbitrary details returned by the service or
            produced by the checker.
    """

    name: str
    status: HealthStatus
    latency_ms: float = 0.0
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "last_check": self.last_check.isoformat(),
            "details": self.details,
        }


# ------------------------------------------------------------------
# Health checker
# ------------------------------------------------------------------


class HealthChecker:
    """Performs health checks on services via the service bus.

    The checker sends a ``health`` action to each service and
    interprets the response to determine :class:`HealthStatus`.

    Latency thresholds:
    - < ``degraded_threshold_ms`` -> HEALTHY
    - < ``unhealthy_threshold_ms`` -> DEGRADED
    - >= ``unhealthy_threshold_ms`` -> UNHEALTHY

    Example::

        checker = HealthChecker(bus, discovery)
        health = checker.check_service("classifier")
        print(health.status)  # HealthStatus.HEALTHY
    """

    def __init__(
        self,
        service_bus: ServiceBus,
        discovery: ServiceDiscovery | None = None,
        degraded_threshold_ms: float = 500.0,
        unhealthy_threshold_ms: float = 2000.0,
    ) -> None:
        """Initialize the health checker.

        Args:
            service_bus: Bus used to send health-check requests.
            discovery: Optional service discovery for listing all
                known services.
            degraded_threshold_ms: Latency above this value (ms)
                triggers DEGRADED status.
            unhealthy_threshold_ms: Latency above this value (ms)
                triggers UNHEALTHY status.
        """
        self._bus = service_bus
        self._discovery = discovery
        self._degraded_ms = degraded_threshold_ms
        self._unhealthy_ms = unhealthy_threshold_ms
        self._history: dict[str, list[ServiceHealth]] = {}
        self._max_history = 100

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def degraded_threshold_ms(self) -> float:
        """Latency threshold (ms) for DEGRADED status."""
        return self._degraded_ms

    @property
    def unhealthy_threshold_ms(self) -> float:
        """Latency threshold (ms) for UNHEALTHY status."""
        return self._unhealthy_ms

    # ------------------------------------------------------------------
    # Core checks
    # ------------------------------------------------------------------

    def check_service(self, name: str) -> ServiceHealth:
        """Check the health of a single service.

        Sends a ``health`` action via the service bus and derives the
        health status from the response.

        Args:
            name: Name of the service to check.

        Returns:
            :class:`ServiceHealth` with the result.
        """
        if not self._bus.has_service(name):
            health = ServiceHealth(
                name=name,
                status=HealthStatus.UNKNOWN,
                details={"error": f"Service '{name}' not registered"},
            )
            self._record(health)
            return health

        start = time.monotonic()
        response = self._bus.send_request(
            target=name,
            action="health",
            payload={},
            timeout=self._unhealthy_ms / 1000.0,
        )
        latency = (time.monotonic() - start) * 1000.0

        if not response.success:
            health = ServiceHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                details={"error": response.error or "Unknown failure"},
            )
        else:
            status = self._resolve_status(latency)
            health = ServiceHealth(
                name=name,
                status=status,
                latency_ms=latency,
                details=response.data,
            )

        self._record(health)
        return health

    def check_all(self) -> dict[str, ServiceHealth]:
        """Check all known services.

        If a :class:`ServiceDiscovery` was provided, services are
        drawn from the discovery registry.  Otherwise, only services
        registered on the bus are checked.

        Returns:
            Dictionary mapping service name to health result.
        """
        names: set[str] = set()

        # From bus
        names.update(self._bus.list_services())

        # From discovery
        if self._discovery is not None:
            for info in self._discovery.list_services():
                names.add(info.name)

        results: dict[str, ServiceHealth] = {}
        for name in sorted(names):
            results[name] = self.check_service(name)
        return results

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, name: str) -> list[ServiceHealth]:
        """Return the check history for a service.

        Args:
            name: Service name.

        Returns:
            List of :class:`ServiceHealth` results (oldest first).
        """
        return list(self._history.get(name, []))

    def clear_history(self, name: str | None = None) -> int:
        """Clear health-check history.

        Args:
            name: If provided, clear only that service's history.
                Otherwise clear all.

        Returns:
            Number of entries removed.
        """
        if name is not None:
            entries = self._history.pop(name, [])
            return len(entries)
        total = sum(len(v) for v in self._history.values())
        self._history.clear()
        return total

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_status(self, latency_ms: float) -> HealthStatus:
        """Determine health status from latency.

        Args:
            latency_ms: Observed latency in milliseconds.

        Returns:
            Resolved :class:`HealthStatus`.
        """
        if latency_ms >= self._unhealthy_ms:
            return HealthStatus.UNHEALTHY
        if latency_ms >= self._degraded_ms:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    def _record(self, health: ServiceHealth) -> None:
        """Append a health result to the history ring buffer."""
        entries = self._history.setdefault(health.name, [])
        entries.append(health)
        if len(entries) > self._max_history:
            entries.pop(0)

    def __repr__(self) -> str:
        checked = len(self._history)
        return (
            f"HealthChecker(checked_services={checked}, "
            f"degraded_ms={self._degraded_ms}, "
            f"unhealthy_ms={self._unhealthy_ms})"
        )
