"""Integration registry and orchestration."""
from __future__ import annotations

from threading import RLock
from typing import Any

from file_organizer.integrations.base import Integration, IntegrationConfig, IntegrationStatus


class IntegrationManager:
    """Thread-safe integration registry used by API and CLI workflows."""

    def __init__(self) -> None:
        self._integrations: dict[str, Integration] = {}
        self._lock = RLock()

    def register(self, integration: Integration) -> None:
        """Register or replace integration by config name."""
        with self._lock:
            self._integrations[integration.config.name] = integration

    def unregister(self, name: str) -> None:
        """Remove an integration from the manager."""
        with self._lock:
            self._integrations.pop(name, None)

    def get(self, name: str) -> Integration | None:
        """Return integration by name if registered."""
        with self._lock:
            return self._integrations.get(name)

    def names(self) -> list[str]:
        """Return integration names in stable order."""
        with self._lock:
            return sorted(self._integrations)

    def list_configs(self) -> list[IntegrationConfig]:
        """Return integration configurations for all registered adapters."""
        with self._lock:
            return [self._integrations[name].config for name in sorted(self._integrations)]

    async def list_statuses(self) -> list[IntegrationStatus]:
        """Return runtime statuses for all integrations."""
        with self._lock:
            integrations = [self._integrations[name] for name in sorted(self._integrations)]
        statuses: list[IntegrationStatus] = []
        for integration in integrations:
            statuses.append(await integration.get_status())
        return statuses

    async def connect(self, name: str) -> bool:
        """Connect one integration and return success state."""
        integration = self.get(name)
        if integration is None:
            return False
        return await integration.connect()

    async def disconnect(self, name: str) -> bool:
        """Disconnect one integration and return success state."""
        integration = self.get(name)
        if integration is None:
            return False
        await integration.disconnect()
        return True

    async def connect_all(self) -> dict[str, bool]:
        """Attempt connection for all enabled integrations."""
        results: dict[str, bool] = {}
        with self._lock:
            integrations = [(name, self._integrations[name]) for name in sorted(self._integrations)]
        for name, integration in integrations:
            if not integration.config.enabled:
                results[name] = False
                continue
            results[name] = await integration.connect()
        return results

    async def disconnect_all(self) -> None:
        """Disconnect every registered integration."""
        with self._lock:
            integrations = [self._integrations[name] for name in sorted(self._integrations)]
        for integration in integrations:
            await integration.disconnect()

    async def send_file(
        self,
        name: str,
        file_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send one file through the named integration."""
        integration = self.get(name)
        if integration is None:
            return False
        if not integration.connected and not await integration.connect():
            return False
        return await integration.send_file(file_path, metadata=metadata)

    def update_settings(self, name: str, settings: dict[str, Any]) -> bool:
        """Merge settings into integration config and reset connection state."""
        with self._lock:
            integration = self._integrations.get(name)
            if integration is None:
                return False
            integration.config.merge_settings(settings)
            integration.connected = False
            return True
