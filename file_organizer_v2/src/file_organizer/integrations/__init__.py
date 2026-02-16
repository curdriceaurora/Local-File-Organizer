"""Third-party integration framework package."""

from file_organizer.integrations.base import (
    Integration,
    IntegrationConfig,
    IntegrationStatus,
    IntegrationType,
)
from file_organizer.integrations.browser import BrowserExtensionManager
from file_organizer.integrations.manager import IntegrationManager
from file_organizer.integrations.obsidian import ObsidianIntegration
from file_organizer.integrations.vscode import VSCodeIntegration
from file_organizer.integrations.workflow import WorkflowIntegration

__all__ = [
    "BrowserExtensionManager",
    "Integration",
    "IntegrationConfig",
    "IntegrationManager",
    "IntegrationStatus",
    "IntegrationType",
    "ObsidianIntegration",
    "VSCodeIntegration",
    "WorkflowIntegration",
]
