"""Terminal User Interface for File Organizer."""
from __future__ import annotations

from file_organizer.tui.analytics_view import AnalyticsView
from file_organizer.tui.app import FileOrganizerApp, run_tui
from file_organizer.tui.file_browser import (
    FileBrowserTree,
    FileBrowserView,
    FileMetadataPanel,
    FilterInput,
)
from file_organizer.tui.file_preview import (
    FilePreviewPanel,
    FilePreviewView,
    FileSelectionManager,
)
from file_organizer.tui.methodology_view import MethodologyView
from file_organizer.tui.organization_preview import OrganizationPreviewView

__all__ = [
    "AnalyticsView",
    "FileOrganizerApp",
    "FileBrowserTree",
    "FileBrowserView",
    "FileMetadataPanel",
    "FilePreviewPanel",
    "FilePreviewView",
    "FileSelectionManager",
    "FilterInput",
    "MethodologyView",
    "OrganizationPreviewView",
    "run_tui",
]
