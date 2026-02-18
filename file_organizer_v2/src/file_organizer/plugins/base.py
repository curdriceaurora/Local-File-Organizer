"""Plugin base contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from file_organizer.plugins.security import PluginSandbox


@dataclass(frozen=True)
class PluginMetadata:
    """Immutable metadata describing plugin identity and compatibility."""

    name: str
    version: str
    author: str
    description: str
    homepage: str | None = None
    license: str = "MIT"
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    min_organizer_version: str = "2.0.0"
    max_organizer_version: str | None = None


class Plugin(ABC):
    """Base interface all plugins must implement."""

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        *,
        sandbox: PluginSandbox | None = None,
    ) -> None:
        self.config: dict[str, Any] = dict(config or {})
        self.sandbox = sandbox or PluginSandbox(plugin_name=self.__class__.__name__)
        self._enabled = False

    @property
    def enabled(self) -> bool:
        """Return whether the plugin is active."""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Set runtime activation state for lifecycle orchestration."""
        self._enabled = enabled

    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""

    @abstractmethod
    def on_load(self) -> None:
        """Handle load lifecycle event."""

    @abstractmethod
    def on_enable(self) -> None:
        """Handle enable lifecycle event."""

    @abstractmethod
    def on_disable(self) -> None:
        """Handle disable lifecycle event."""

    @abstractmethod
    def on_unload(self) -> None:
        """Handle unload lifecycle event."""
