"""Core contracts for third-party integrations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntegrationType(str, Enum):
    """Supported categories for external integrations."""

    DESKTOP_APP = "desktop_app"
    EDITOR = "editor"
    WORKFLOW = "workflow"
    BROWSER = "browser"
    API = "api"


@dataclass
class IntegrationConfig:
    """Runtime configuration for a single integration adapter."""

    name: str
    integration_type: IntegrationType
    enabled: bool = True
    auth_method: str = "none"
    settings: dict[str, Any] = field(default_factory=dict)

    def merge_settings(self, updates: dict[str, Any]) -> None:
        """Apply partial settings update in-place."""
        self.settings.update(updates)


@dataclass(frozen=True)
class IntegrationStatus:
    """Serializable runtime status for integrations list/status APIs."""

    name: str
    integration_type: IntegrationType
    enabled: bool
    connected: bool
    details: dict[str, Any] = field(default_factory=dict)


class Integration(ABC):
    """Base contract all integrations must satisfy."""

    def __init__(self, config: IntegrationConfig) -> None:
        self.config = config
        self.connected = False

    @abstractmethod
    async def connect(self) -> bool:
        """Initialize the integration and validate preconditions."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear down integration resources."""

    @abstractmethod
    async def validate_auth(self) -> bool:
        """Validate configured authentication details, if required."""

    @abstractmethod
    async def send_file(self, file_path: str, metadata: dict[str, Any] | None = None) -> bool:
        """Send or expose a file to the target integration."""

    @abstractmethod
    async def get_status(self) -> IntegrationStatus:
        """Return runtime integration status with implementation details."""
