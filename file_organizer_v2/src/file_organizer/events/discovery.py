"""Service discovery with JSON file-based registry.

Provides local service registration, lookup, and heartbeat
tracking using a JSON file as the persistent store.  Designed
for privacy-first, single-machine deployments where an external
service registry is not desired.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default registry path relative to working directory
_DEFAULT_REGISTRY = Path(".file_organizer") / "service_registry.json"


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass
class ServiceInfo:
    """Metadata for a registered service.

    Attributes:
        name: Unique service name.
        endpoint: Address or identifier for reaching the service.
        metadata: Arbitrary key-value metadata supplied at registration.
        registered_at: UTC timestamp of initial registration.
        last_heartbeat: UTC timestamp of the most recent heartbeat.
    """

    name: str
    endpoint: str
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at: str = ""
    last_heartbeat: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.registered_at:
            self.registered_at = now
        if not self.last_heartbeat:
            self.last_heartbeat = now

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceInfo:
        """Reconstruct a :class:`ServiceInfo` from a dictionary.

        Args:
            data: Dictionary as produced by :meth:`to_dict`.

        Returns:
            New ``ServiceInfo`` instance.
        """
        return cls(
            name=data["name"],
            endpoint=data["endpoint"],
            metadata=data.get("metadata", {}),
            registered_at=data.get("registered_at", ""),
            last_heartbeat=data.get("last_heartbeat", ""),
        )


# ------------------------------------------------------------------
# Discovery
# ------------------------------------------------------------------


class ServiceDiscovery:
    """File-backed service discovery registry.

    All state is persisted to a JSON file so that services can find
    each other across restarts without requiring an external
    coordinator.

    Example::

        disc = ServiceDiscovery()
        disc.register("classifier", "local://classifier:8001",
                       {"version": "1.0"})
        info = disc.discover("classifier")
        assert info is not None
        disc.heartbeat("classifier")
        disc.deregister("classifier")
    """

    def __init__(self, registry_path: Path | None = None) -> None:
        """Initialize discovery with a file-based registry.

        Args:
            registry_path: Path to the JSON registry file.  Created
                automatically if it does not exist.
        """
        self._path = registry_path or _DEFAULT_REGISTRY
        self._services: dict[str, ServiceInfo] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load the registry from disk."""
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                self._services = {name: ServiceInfo.from_dict(entry) for name, entry in raw.items()}
                logger.debug(
                    "Loaded %d services from %s",
                    len(self._services),
                    self._path,
                )
            except (json.JSONDecodeError, KeyError):
                logger.warning("Corrupt registry at %s; starting fresh", self._path)
                self._services = {}
        else:
            self._services = {}

    def _save(self) -> None:
        """Persist the current registry to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {name: info.to_dict() for name, info in self._services.items()}
        self._path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        logger.debug("Saved %d services to %s", len(self._services), self._path)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        endpoint: str,
        metadata: dict[str, Any] | None = None,
    ) -> ServiceInfo:
        """Register a service in the discovery registry.

        If a service with the same name already exists, it is
        overwritten.

        Args:
            name: Unique service name.
            endpoint: Address string for the service.
            metadata: Optional metadata dictionary.

        Returns:
            The :class:`ServiceInfo` that was stored.
        """
        info = ServiceInfo(
            name=name,
            endpoint=endpoint,
            metadata=metadata or {},
        )
        self._services[name] = info
        self._save()
        logger.info("Registered service '%s' at '%s'", name, endpoint)
        return info

    def deregister(self, name: str) -> bool:
        """Remove a service from the registry.

        Args:
            name: Service name to remove.

        Returns:
            ``True`` if the service was found and removed.
        """
        if name in self._services:
            del self._services[name]
            self._save()
            logger.info("Deregistered service '%s'", name)
            return True
        return False

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def discover(self, name: str) -> ServiceInfo | None:
        """Look up a service by name.

        Args:
            name: Service name.

        Returns:
            :class:`ServiceInfo` if found, ``None`` otherwise.
        """
        return self._services.get(name)

    def list_services(self) -> list[ServiceInfo]:
        """Return all registered services.

        Returns:
            List of :class:`ServiceInfo` objects sorted by name.
        """
        return sorted(self._services.values(), key=lambda s: s.name)

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def heartbeat(self, name: str) -> bool:
        """Update the last-heartbeat timestamp for a service.

        Args:
            name: Service name.

        Returns:
            ``True`` if the service exists and was updated.
        """
        info = self._services.get(name)
        if info is None:
            logger.warning("Heartbeat for unknown service '%s'", name)
            return False
        info.last_heartbeat = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.debug("Heartbeat updated for '%s'", name)
        return True

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Number of registered services."""
        return len(self._services)

    @property
    def registry_path(self) -> Path:
        """Path to the JSON registry file."""
        return self._path

    def clear(self) -> int:
        """Remove all services from the registry.

        Returns:
            Number of services that were removed.
        """
        count = len(self._services)
        self._services.clear()
        self._save()
        return count

    def __repr__(self) -> str:
        return f"ServiceDiscovery(services={len(self._services)}, path={self._path!r})"
