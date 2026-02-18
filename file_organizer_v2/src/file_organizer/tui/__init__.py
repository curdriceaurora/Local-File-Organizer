"""Terminal User Interface for File Organizer."""

from __future__ import annotations

from file_organizer.tui.analytics_view import AnalyticsView
from file_organizer.tui.app import FileOrganizerApp, run_tui
from file_organizer.tui.audio_view import AudioView
from file_organizer.tui.copilot_view import CopilotView
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
from file_organizer.tui.undo_history_view import UndoHistoryView

__all__ = [
    "AnalyticsView",
    "AudioView",
    "CopilotView",
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
    "UndoHistoryView",
    "run_tui",
]
