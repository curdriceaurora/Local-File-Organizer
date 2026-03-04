"""Tests for file_organizer.tui.methodology_view module.

Covers MethodologySelectorPanel, MethodologyPreviewPanel, and MethodologyView
initialization, preview display, methodology switching, and status updates.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from file_organizer.tui.methodology_view import (
    MethodologyPreviewPanel,
    MethodologySelectorPanel,
    MethodologyView,
)

pytestmark = [pytest.mark.unit]


# -----------------------------------------------------------------------
# MethodologySelectorPanel
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestMethodologySelectorPanel:
    """Test MethodologySelectorPanel widget."""

    def test_inherits_from_static(self) -> None:
        """Test that MethodologySelectorPanel extends Static."""
        assert issubclass(MethodologySelectorPanel, Static)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "MethodologySelectorPanel" in MethodologySelectorPanel.DEFAULT_CSS

    def test_has_methods_dictionary(self) -> None:
        """Test that methods dictionary is defined."""
        assert hasattr(MethodologySelectorPanel, "_METHODS")
        methods = MethodologySelectorPanel._METHODS
        assert "none" in methods
        assert "para" in methods
        assert "jd" in methods

    def test_initial_methodology_is_none(self) -> None:
        """Test that default methodology is 'none'."""
        panel = MethodologySelectorPanel()
        assert panel._current == "none"

    def test_current_methodology_property(self) -> None:
        """Test current_methodology property."""
        panel = MethodologySelectorPanel()
        assert panel.current_methodology == "none"

    def test_set_methodology_changes_state(self) -> None:
        """Test set_methodology changes the current methodology."""
        panel = MethodologySelectorPanel()
        panel.update = MagicMock()
        panel.set_methodology("para")
        assert panel._current == "para"
        panel.update.assert_called()

    def test_render_selector_displays_current_methodology(self) -> None:
        """Test that render_selector highlights current methodology."""
        panel = MethodologySelectorPanel()
        panel.update = MagicMock()
        panel._render_selector()
        rendered = panel.update.call_args[0][0]
        assert "Methodology Selector" in rendered
        assert "[bold green]>[/bold green]" in rendered

    def test_render_selector_shows_all_options(self) -> None:
        """Test that all methodology options are shown."""
        panel = MethodologySelectorPanel()
        panel.update = MagicMock()
        panel._render_selector()
        rendered = panel.update.call_args[0][0]
        assert "[n]" in rendered
        assert "[p]" in rendered
        assert "[j]" in rendered

    def test_on_mount_renders_initial_state(self) -> None:
        """Test that on_mount triggers initial render."""
        panel = MethodologySelectorPanel()
        panel.update = MagicMock()
        panel.on_mount()
        panel.update.assert_called()

    def test_set_multiple_methodologies(self) -> None:
        """Test switching between methodologies."""
        panel = MethodologySelectorPanel()
        panel.update = MagicMock()

        panel.set_methodology("para")
        assert panel.current_methodology == "para"

        panel.set_methodology("jd")
        assert panel.current_methodology == "jd"

        panel.set_methodology("none")
        assert panel.current_methodology == "none"


# -----------------------------------------------------------------------
# MethodologyPreviewPanel
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestMethodologyPreviewPanel:
    """Test MethodologyPreviewPanel widget."""

    def test_inherits_from_static(self) -> None:
        """Test that MethodologyPreviewPanel extends Static."""
        assert issubclass(MethodologyPreviewPanel, Static)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "MethodologyPreviewPanel" in MethodologyPreviewPanel.DEFAULT_CSS

    def test_show_none_preview(self) -> None:
        """Test show_none_preview displays no methodology message."""
        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        panel.show_none_preview()
        rendered = panel.update.call_args[0][0]
        assert "No Methodology" in rendered
        assert "AI-suggested categories" in rendered

    def test_show_para_preview_empty(self) -> None:
        """Test show_para_preview with no distribution data."""
        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        panel.show_para_preview(None)
        rendered = panel.update.call_args[0][0]
        assert "PARA Preview" in rendered
        assert "No files analyzed" in rendered

    def test_show_para_preview_with_distribution(self) -> None:
        """Test show_para_preview with distribution data."""
        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        distribution = {
            "Projects": 50,
            "Areas": 30,
            "Resources": 15,
            "Archive": 5,
        }
        panel.show_para_preview(distribution)
        rendered = panel.update.call_args[0][0]
        assert "PARA Preview" in rendered
        assert "Projects" in rendered
        assert "Areas" in rendered
        assert "50" in rendered
        assert "[green]" in rendered  # Bar color

    def test_show_para_preview_empty_distribution(self) -> None:
        """Test show_para_preview with empty dictionary."""
        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        panel.show_para_preview({})
        rendered = panel.update.call_args[0][0]
        assert "PARA Preview" in rendered

    def test_show_jd_preview_empty(self) -> None:
        """Test show_jd_preview with no data."""
        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        panel.show_jd_preview(None, None)
        rendered = panel.update.call_args[0][0]
        assert "Johnny Decimal Preview" in rendered
        assert "No scheme configured" in rendered

    def test_show_jd_preview_with_areas(self) -> None:
        """Test show_jd_preview with areas data."""
        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        areas = {
            10: "Finance",
            20: "Projects",
            30: "Archive",
        }
        panel.show_jd_preview(areas, None)
        rendered = panel.update.call_args[0][0]
        assert "Johnny Decimal Preview" in rendered
        assert "10-19" in rendered
        assert "Finance" in rendered
        assert "[bold cyan]" in rendered

    def test_show_jd_preview_with_areas_and_categories(self) -> None:
        """Test show_jd_preview with both areas and categories."""
        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        areas = {10: "Finance"}
        categories = {"10": "Bank Accounts", "11": "Investments"}
        panel.show_jd_preview(areas, categories)
        rendered = panel.update.call_args[0][0]
        assert "Finance" in rendered
        assert "10" in rendered

    def test_show_loading(self) -> None:
        """Test show_loading displays loading state."""
        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        panel.show_loading()
        rendered = panel.update.call_args[0][0]
        assert "Loading preview" in rendered

    def test_show_error(self) -> None:
        """Test show_error displays error message."""
        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        panel.show_error("Test error message")
        rendered = panel.update.call_args[0][0]
        assert "Error:" in rendered
        assert "Test error message" in rendered
        assert "[red]" in rendered


# -----------------------------------------------------------------------
# MethodologyView
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestMethodologyView:
    """Test MethodologyView widget."""

    def test_inherits_from_vertical(self) -> None:
        """Test that MethodologyView extends Vertical."""
        assert issubclass(MethodologyView, Vertical)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "MethodologyView" in MethodologyView.DEFAULT_CSS

    def test_bindings_defined(self) -> None:
        """Test that all bindings are defined."""
        bindings = [b for b in MethodologyView.BINDINGS if isinstance(b, Binding)]
        keys = [b.key for b in bindings]
        assert "p" in keys  # PARA
        assert "j" in keys  # Johnny Decimal
        assert "n" in keys  # None
        assert "m" in keys  # Migrate

    def test_initialization_with_default_directory(self) -> None:
        """Test MethodologyView initialization with default directory."""
        view = MethodologyView()
        assert view._scan_dir == Path(".")
        assert view._methodology == "none"

    def test_initialization_with_custom_directory(self) -> None:
        """Test MethodologyView initialization with custom directory."""
        test_path = Path("/tmp/test")
        view = MethodologyView(scan_dir=test_path)
        assert view._scan_dir == test_path

    def test_initialization_with_string_directory(self) -> None:
        """Test MethodologyView initialization with string directory."""
        view = MethodologyView(scan_dir="/tmp/test")
        assert view._scan_dir == Path("/tmp/test")

    def test_has_compose_method(self) -> None:
        """Test that compose method is defined."""
        assert callable(getattr(MethodologyView, "compose", None))

    def test_has_on_mount_method(self) -> None:
        """Test that on_mount method is defined."""
        assert callable(getattr(MethodologyView, "on_mount", None))

    def test_has_action_set_para(self) -> None:
        """Test that action_set_para is defined."""
        assert callable(getattr(MethodologyView, "action_set_para", None))

    def test_has_action_set_jd(self) -> None:
        """Test that action_set_jd is defined."""
        assert callable(getattr(MethodologyView, "action_set_jd", None))

    def test_has_action_set_none(self) -> None:
        """Test that action_set_none is defined."""
        assert callable(getattr(MethodologyView, "action_set_none", None))

    def test_has_action_migrate(self) -> None:
        """Test that action_migrate is defined."""
        assert callable(getattr(MethodologyView, "action_migrate", None))

    def test_has_update_preview_method(self) -> None:
        """Test that _update_preview method is defined."""
        assert callable(getattr(MethodologyView, "_update_preview", None))

    def test_has_set_status_method(self) -> None:
        """Test that _set_status method is defined."""
        assert callable(getattr(MethodologyView, "_set_status", None))

    def test_custom_widget_attributes(self) -> None:
        """Test that custom attributes are properly set."""
        view = MethodologyView(name="test-view", id="methodology-main")
        assert view.name == "test-view"
        assert view.id == "methodology-main"

    def test_max_sample_files_constant(self) -> None:
        """Test that max sample files constant is defined."""
        assert hasattr(MethodologyView, "_MAX_SAMPLE_FILES")
        assert MethodologyView._MAX_SAMPLE_FILES == 200

    def test_action_migrate_sets_status(self) -> None:
        """Test that action_migrate sets status message."""
        view = MethodologyView()
        view._set_status = MagicMock()
        view.action_migrate()
        view._set_status.assert_called()
