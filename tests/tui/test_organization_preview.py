"""Tests for file_organizer.tui.organization_preview module.

Covers BeforeAfterPanel, OrganizationSummary, OrganizationPreviewView
initialization, preview display, and organization actions.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

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
        panel.set_structure(structure, input_dir="/home/user/files")  # noqa: test-hardcoded-paths
        rendered = panel.update.call_args[0][0]
        assert "/home/user/files/file.pdf" in rendered  # noqa: test-hardcoded-paths

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

    @pytest.mark.keep_default_paths
    def test_initialization_with_defaults(self) -> None:
        """Test OrganizationPreviewView with default directories."""
        view = OrganizationPreviewView()
        assert view._input_dir == Path(".")
        assert view._output_dir == Path("organized_output")

    def test_initialization_with_custom_directories(self) -> None:
        """Test OrganizationPreviewView with custom directories."""
        input_path = Path("/") / "home" / "user" / "files"  # noqa: test-hardcoded-paths
        output_path = Path("/") / "home" / "user" / "organized"  # noqa: test-hardcoded-paths
        view = OrganizationPreviewView(input_dir=input_path, output_dir=output_path)
        assert view._input_dir == input_path
        assert view._output_dir == output_path

    def test_initialization_with_string_directories(self) -> None:
        """Test OrganizationPreviewView with string directories."""
        view = OrganizationPreviewView(
            input_dir="/tmp/input",  # noqa: test-hardcoded-paths
            output_dir="/tmp/output",  # noqa: test-hardcoded-paths
        )
        assert view._input_dir == Path("/") / "tmp" / "input"  # noqa: test-hardcoded-paths
        assert view._output_dir == Path("/") / "tmp" / "output"  # noqa: test-hardcoded-paths

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
        view.query_one = MagicMock()
        view._apply_organization = MagicMock()
        view._set_status = MagicMock()
        view.action_confirm()
        view._set_status.assert_called()

    def test_action_cancel_sets_status(self) -> None:
        """Test that action_cancel sets status message."""
        view = OrganizationPreviewView()
        view._set_status = MagicMock()
        view.action_cancel()
        view._set_status.assert_called_with("Ready")
    def test_compose_yields_widgets(self) -> None:
        view = OrganizationPreviewView()
        widgets = list(view.compose())
        assert len(widgets) == 3

    def test_on_mount_calls_load_preview(self) -> None:
        view = OrganizationPreviewView()
        view._load_preview = MagicMock()
        view.on_mount()
        view._load_preview.assert_called_once()

    def test_action_refresh_preview(self) -> None:
        view = OrganizationPreviewView()
        view.query_one = MagicMock()
        view._load_preview = MagicMock()
        view.action_refresh_preview()
        assert view.query_one.call_count == 2
        view._load_preview.assert_called_once()

    def test_action_confirm_when_already_applying(self) -> None:
        view = OrganizationPreviewView()
        view._is_applying = True
        view._set_status = MagicMock()
        view.action_confirm()
        view._set_status.assert_called_with("Organization is already applying...")

    @patch("tests.tui.test_organization_preview.OrganizationPreviewView.app", new_callable=PropertyMock)
    def test_handle_apply_success(self, mock_app) -> None:
        view = OrganizationPreviewView()
        view.query_one = MagicMock()
        view._set_status = MagicMock()

        class MockResult:
            organized_structure = {"A": ["b.txt"]}
            total_files = 1
            processed_files = 1
            skipped_files = 0
            failed_files = 0
            errors = []

        view._handle_apply_success(MockResult())
        assert not view._is_applying
        assert view.query_one.call_count == 2
        view._set_status.assert_called_with("Organization applied. Opening history.")

    def test_handle_apply_error(self) -> None:
        view = OrganizationPreviewView()
        view.query_one = MagicMock()
        view._set_status = MagicMock()
        view._handle_apply_error(Exception("Test error"))
        assert not view._is_applying
        assert view.query_one.call_count == 2
        view._set_status.assert_called_with("Apply failed")

    def test_set_status_no_app(self) -> None:
        view = OrganizationPreviewView()
        view._set_status("test message")  # Should safely ignore missing app

    @pytest.mark.asyncio
    async def test_load_preview_success(self) -> None:
        from textual.app import App

        class MockApp(App):
            pass

        with patch("file_organizer.core.organizer.FileOrganizer") as mock_org, \
             patch("file_organizer.tui.organization_preview.load_parallel_runtime_settings") as mock_settings:

            mock_settings.return_value.max_workers = 2
            mock_settings.return_value.prefetch_depth = 4

            mock_instance = mock_org.return_value
            class MockResult:
                organized_structure = {"A": ["b.txt"]}
                total_files = 1
                processed_files = 1
                skipped_files = 0
                failed_files = 0
                errors = []
            mock_instance.organize.return_value = MockResult()

            app = MockApp()
            async with app.run_test():
                view = OrganizationPreviewView()
                await app.mount(view)

                for worker in view.workers:
                    await worker.wait()

                mock_instance.organize.assert_called_once_with(
                    input_path=view._input_dir,
                    output_path=view._output_dir,
                )

                panel = view.query_one(BeforeAfterPanel)
                assert "A/" in str(panel.render())

    @pytest.mark.asyncio
    async def test_load_preview_error(self) -> None:
        from textual.app import App

        class MockApp(App):
            pass

        with patch("file_organizer.core.organizer.FileOrganizer") as mock_org, \
             patch("file_organizer.tui.organization_preview.load_parallel_runtime_settings") as mock_settings:

            mock_settings.return_value.max_workers = 2
            mock_settings.return_value.prefetch_depth = 4

            mock_instance = mock_org.return_value
            mock_instance.organize.side_effect = Exception("test error")

            app = MockApp()
            async with app.run_test():
                view = OrganizationPreviewView()
                await app.mount(view)

                for worker in view.workers:
                    await worker.wait()

                panel = view.query_one(BeforeAfterPanel)
                rendered = str(panel.render())
                assert "Models unavailable" in rendered
                assert "test error" in rendered

    @pytest.mark.asyncio
    async def test_apply_organization_success(self) -> None:
        from textual.app import App

        class MockApp(App):
            action_switch_view = MagicMock()

        with patch("file_organizer.core.organizer.FileOrganizer") as mock_org, \
             patch("file_organizer.tui.organization_preview.load_parallel_runtime_settings") as mock_settings:

            mock_settings.return_value.max_workers = 2
            mock_settings.return_value.prefetch_depth = 4

            mock_instance = mock_org.return_value
            class MockResult:
                organized_structure = {"A": ["b.txt"]}
                total_files = 1
                processed_files = 1
                skipped_files = 0
                failed_files = 0
                errors = []
            mock_instance.organize.return_value = MockResult()

            app = MockApp()
            async with app.run_test():
                view = OrganizationPreviewView()
                await app.mount(view)

                for worker in view.workers:
                    await worker.wait()

                mock_instance.organize.reset_mock()

                view.action_confirm()

                for worker in view.workers:
                    await worker.wait()

                mock_instance.organize.assert_called_once_with(
                    input_path=view._input_dir,
                    output_path=view._output_dir,
                )

                app.action_switch_view.assert_called_once_with("history")

    @pytest.mark.asyncio
    async def test_apply_organization_error(self) -> None:
        from textual.app import App

        class MockApp(App):
            action_switch_view = MagicMock()

        with patch("file_organizer.core.organizer.FileOrganizer") as mock_org, \
             patch("file_organizer.tui.organization_preview.load_parallel_runtime_settings") as mock_settings:

            mock_settings.return_value.max_workers = 2
            mock_settings.return_value.prefetch_depth = 4

            mock_instance = mock_org.return_value
            class MockResult:
                organized_structure = {"A": ["b.txt"]}
                total_files = 1
                processed_files = 1
                skipped_files = 0
                failed_files = 0
                errors = []
            mock_instance.organize.return_value = MockResult()

            app = MockApp()
            async with app.run_test():
                view = OrganizationPreviewView()
                await app.mount(view)

                for worker in view.workers:
                    await worker.wait()

                mock_instance.organize.side_effect = Exception("apply error")

                view.action_confirm()

                for worker in view.workers:
                    await worker.wait()

                panel = view.query_one(BeforeAfterPanel)
                rendered = str(panel.render())
                assert "Apply failed" in rendered
                assert "apply error" in rendered
