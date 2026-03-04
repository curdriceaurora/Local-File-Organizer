"""Tests for file_organizer.tui.organization_preview module.

Covers BeforeAfterPanel, OrganizationSummary, OrganizationPreviewView
initialization, preview display, and organization actions.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from file_organizer.tui.organization_preview import (
    BeforeAfterPanel,
    OrganizationPreviewView,
    OrganizationSummary,
)

pytestmark = [pytest.mark.unit]


# -----------------------------------------------------------------------
# BeforeAfterPanel
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestBeforeAfterPanel:
    """Test BeforeAfterPanel widget."""

    def test_inherits_from_static(self) -> None:
        """Test that BeforeAfterPanel extends Static."""
        assert issubclass(BeforeAfterPanel, Static)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "BeforeAfterPanel" in BeforeAfterPanel.DEFAULT_CSS

    def test_set_structure_empty(self) -> None:
        """Test set_structure with empty structure."""
        panel = BeforeAfterPanel()
        panel.update = MagicMock()
        panel.set_structure({})
        rendered = panel.update.call_args[0][0]
        assert "No files to organize" in rendered

    def test_set_structure_with_single_folder(self) -> None:
        """Test set_structure with single folder."""
        panel = BeforeAfterPanel()
        panel.update = MagicMock()
        structure = {
            "Documents": ["file1.pdf", "file2.pdf"],
        }
        panel.set_structure(structure)
        rendered = panel.update.call_args[0][0]
        assert "Before -> After" in rendered
        assert "Documents" in rendered
        assert "file1.pdf" in rendered
        assert "file2.pdf" in rendered

    def test_set_structure_with_multiple_folders(self) -> None:
        """Test set_structure with multiple folders."""
        panel = BeforeAfterPanel()
        panel.update = MagicMock()
        structure = {
            "Documents": ["doc1.pdf"],
            "Images": ["img1.jpg"],
            "Videos": ["vid1.mp4"],
        }
        panel.set_structure(structure)
        rendered = panel.update.call_args[0][0]
        assert "Documents" in rendered
        assert "Images" in rendered
        assert "Videos" in rendered

    def test_set_structure_with_input_dir(self) -> None:
        """Test set_structure includes source path."""
        panel = BeforeAfterPanel()
        panel.update = MagicMock()
        structure = {"Docs": ["file.pdf"]}
        panel.set_structure(structure, input_dir="/home/user/files")
        rendered = panel.update.call_args[0][0]
        assert "/home/user/files/file.pdf" in rendered

    def test_set_structure_truncates_long_lists(self) -> None:
        """Test that large file lists are truncated."""
        panel = BeforeAfterPanel()
        panel.update = MagicMock()
        many_files = [f"file{i}.txt" for i in range(50)]
        structure = {"Docs": many_files}
        panel.set_structure(structure)
        rendered = panel.update.call_args[0][0]
        assert "... and" in rendered
        assert "more" in rendered

    def test_set_structure_arrow_separator(self) -> None:
        """Test that before/after separator is shown."""
        panel = BeforeAfterPanel()
        panel.update = MagicMock()
        structure = {"Docs": ["file.pdf"]}
        panel.set_structure(structure)
        rendered = panel.update.call_args[0][0]
        assert "->" in rendered

    def test_set_structure_folder_color(self) -> None:
        """Test that folder names are colored."""
        panel = BeforeAfterPanel()
        panel.update = MagicMock()
        structure = {"Documents": ["file.pdf"]}
        panel.set_structure(structure)
        rendered = panel.update.call_args[0][0]
        assert "[bold cyan]" in rendered


# -----------------------------------------------------------------------
# OrganizationSummary
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestOrganizationSummary:
    """Test OrganizationSummary widget."""

    def test_inherits_from_static(self) -> None:
        """Test that OrganizationSummary extends Static."""
        assert issubclass(OrganizationSummary, Static)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "OrganizationSummary" in OrganizationSummary.DEFAULT_CSS

    def test_set_result_with_defaults(self) -> None:
        """Test set_result with default parameters."""
        panel = OrganizationSummary()
        panel.update = MagicMock()
        panel.set_result()
        rendered = panel.update.call_args[0][0]
        assert "Organization Summary" in rendered
        assert "Total files:" in rendered
        assert "Processed:" in rendered

    def test_set_result_with_values(self) -> None:
        """Test set_result with custom values."""
        panel = OrganizationSummary()
        panel.update = MagicMock()
        panel.set_result(
            total=100,
            processed=85,
            skipped=10,
            failed=5,
            folders=15,
        )
        rendered = panel.update.call_args[0][0]
        assert "100" in rendered
        assert "85" in rendered
        assert "10" in rendered
        assert "5" in rendered
        assert "15" in rendered

    def test_set_result_with_color_coding(self) -> None:
        """Test that result values have appropriate colors."""
        panel = OrganizationSummary()
        panel.update = MagicMock()
        panel.set_result(processed=50, skipped=25, failed=5)
        rendered = panel.update.call_args[0][0]
        assert "[green]" in rendered  # Processed
        assert "[yellow]" in rendered  # Skipped
        assert "[red]" in rendered  # Failed

    def test_set_result_with_errors(self) -> None:
        """Test set_result with error list."""
        panel = OrganizationSummary()
        panel.update = MagicMock()
        errors = [
            ("file1.txt", "Permission denied"),
            ("file2.txt", "File locked"),
        ]
        panel.set_result(failed=2, errors=errors)
        rendered = panel.update.call_args[0][0]
        assert "Errors:" in rendered
        assert "file1.txt" in rendered
        assert "Permission denied" in rendered

    def test_set_result_truncates_error_list(self) -> None:
        """Test that long error lists are truncated."""
        panel = OrganizationSummary()
        panel.update = MagicMock()
        errors = [(f"file{i}.txt", f"Error {i}") for i in range(10)]
        panel.set_result(failed=10, errors=errors)
        rendered = panel.update.call_args[0][0]
        assert "... and" in rendered
        assert "more" in rendered

    def test_set_result_no_errors_section_if_empty(self) -> None:
        """Test that error section is omitted when no errors."""
        panel = OrganizationSummary()
        panel.update = MagicMock()
        panel.set_result(failed=0, errors=None)
        rendered = panel.update.call_args[0][0]
        assert "Errors:" not in rendered


# -----------------------------------------------------------------------
# OrganizationPreviewView
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestOrganizationPreviewView:
    """Test OrganizationPreviewView widget."""

    def test_inherits_from_vertical(self) -> None:
        """Test that OrganizationPreviewView extends Vertical."""
        assert issubclass(OrganizationPreviewView, Vertical)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "OrganizationPreviewView" in OrganizationPreviewView.DEFAULT_CSS

    def test_bindings_defined(self) -> None:
        """Test that all bindings are defined."""
        bindings = [b for b in OrganizationPreviewView.BINDINGS if isinstance(b, Binding)]
        keys = [b.key for b in bindings]
        assert "r" in keys  # Refresh
        assert "enter" in keys  # Confirm
        assert "escape" in keys  # Cancel

    def test_initialization_with_defaults(self) -> None:
        """Test OrganizationPreviewView with default directories."""
        view = OrganizationPreviewView()
        assert view._input_dir == Path(".")
        assert view._output_dir == Path("organized_output")

    def test_initialization_with_custom_directories(self) -> None:
        """Test OrganizationPreviewView with custom directories."""
        input_path = Path("/home/user/files")
        output_path = Path("/home/user/organized")
        view = OrganizationPreviewView(input_dir=input_path, output_dir=output_path)
        assert view._input_dir == input_path
        assert view._output_dir == output_path

    def test_initialization_with_string_directories(self) -> None:
        """Test OrganizationPreviewView with string directories."""
        view = OrganizationPreviewView(
            input_dir="/tmp/input",
            output_dir="/tmp/output",
        )
        assert view._input_dir == Path("/tmp/input")
        assert view._output_dir == Path("/tmp/output")

    def test_has_compose_method(self) -> None:
        """Test that compose method is defined."""
        assert callable(getattr(OrganizationPreviewView, "compose", None))

    def test_has_on_mount_method(self) -> None:
        """Test that on_mount method is defined."""
        assert callable(getattr(OrganizationPreviewView, "on_mount", None))

    def test_has_action_refresh_preview(self) -> None:
        """Test that action_refresh_preview is defined."""
        assert callable(getattr(OrganizationPreviewView, "action_refresh_preview", None))

    def test_has_action_confirm(self) -> None:
        """Test that action_confirm is defined."""
        assert callable(getattr(OrganizationPreviewView, "action_confirm", None))

    def test_has_action_cancel(self) -> None:
        """Test that action_cancel is defined."""
        assert callable(getattr(OrganizationPreviewView, "action_cancel", None))

    def test_has_set_status_method(self) -> None:
        """Test that _set_status method is defined."""
        assert callable(getattr(OrganizationPreviewView, "_set_status", None))

    def test_has_load_preview_method(self) -> None:
        """Test that _load_preview method is defined."""
        assert callable(getattr(OrganizationPreviewView, "_load_preview", None))

    def test_custom_widget_attributes(self) -> None:
        """Test that custom attributes are properly set."""
        view = OrganizationPreviewView(name="test-view", id="org-preview")
        assert view.name == "test-view"
        assert view.id == "org-preview"

    def test_action_confirm_sets_status(self) -> None:
        """Test that action_confirm sets status message."""
        view = OrganizationPreviewView()
        view._set_status = MagicMock()
        view.action_confirm()
        view._set_status.assert_called()

    def test_action_cancel_sets_status(self) -> None:
        """Test that action_cancel sets status message."""
        view = OrganizationPreviewView()
        view._set_status = MagicMock()
        view.action_cancel()
        view._set_status.assert_called_with("Ready")
