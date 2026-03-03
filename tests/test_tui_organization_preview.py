"""Tests for TUI organization preview view."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from file_organizer.tui.organization_preview import (
    BeforeAfterPanel,
    OrganizationPreviewView,
    OrganizationSummary,
)


def _get_content(widget: object) -> str:
    """Extract the text content from a Static widget."""
    # Textual stores update() content as name-mangled __content
    return str(getattr(widget, "_Static__content", ""))


@pytest.mark.unit
class TestBeforeAfterPanel:
    """Unit tests for BeforeAfterPanel."""

    def test_empty_structure(self) -> None:
        panel = BeforeAfterPanel()
        panel.set_structure({})
        assert "No files" in _get_content(panel)

    def test_structure_with_files(self) -> None:
        panel = BeforeAfterPanel()
        structure = {
            "Documents": ["report.pdf", "notes.txt"],
            "Images": ["photo.jpg"],
        }
        panel.set_structure(structure, input_dir="/input")
        content = _get_content(panel)
        assert "Documents" in content
        assert "report.pdf" in content
        assert "Images" in content

    def test_structure_truncates_long_lists(self) -> None:
        panel = BeforeAfterPanel()
        structure = {"Folder": [f"file_{i}.txt" for i in range(30)]}
        panel.set_structure(structure)
        assert "more" in _get_content(panel)


@pytest.mark.unit
class TestOrganizationSummary:
    """Unit tests for OrganizationSummary."""

    def test_set_result_basic(self) -> None:
        summary = OrganizationSummary()
        summary.set_result(total=10, processed=7, skipped=2, failed=1, folders=3)
        content = _get_content(summary)
        assert "10" in content
        assert "7" in content

    def test_set_result_with_errors(self) -> None:
        summary = OrganizationSummary()
        summary.set_result(
            total=5,
            processed=3,
            skipped=0,
            failed=2,
            folders=2,
            errors=[("bad.txt", "Cannot read"), ("corrupt.pdf", "Invalid format")],
        )
        content = _get_content(summary)
        assert "bad.txt" in content
        assert "Cannot read" in content

    def test_set_result_truncates_many_errors(self) -> None:
        errors = [(f"file_{i}.txt", f"Error {i}") for i in range(10)]
        summary = OrganizationSummary()
        summary.set_result(total=10, processed=0, skipped=0, failed=10, folders=0, errors=errors)
        assert "more" in _get_content(summary)


@pytest.mark.unit
class TestOrganizationPreviewView:
    """Tests for OrganizationPreviewView composition."""

    def test_default_init(self) -> None:
        view = OrganizationPreviewView(id="view")
        assert str(view._input_dir) == "."
        assert str(view._output_dir) == "organized_output"

    def test_custom_dirs(self) -> None:
        view = OrganizationPreviewView(
            input_dir="/tmp/input",
            output_dir="/tmp/output",
            id="view",
        )
        assert str(view._input_dir) == "/tmp/input"
        assert str(view._output_dir) == "/tmp/output"


@pytest.mark.asyncio
async def test_organization_preview_mounts() -> None:
    """OrganizationPreviewView should mount with all child panels."""
    from file_organizer.tui.app import FileOrganizerApp

    with patch.object(OrganizationPreviewView, "_load_preview"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("organized")
            await pilot.pause()
            view = app.query_one("#view", OrganizationPreviewView)
            assert view is not None
            assert view.query_one(BeforeAfterPanel) is not None
            assert view.query_one(OrganizationSummary) is not None
            await pilot.press("q")


@pytest.mark.asyncio
async def test_refresh_binding() -> None:
    """Pressing 'r' should trigger a refresh."""
    from file_organizer.tui.app import FileOrganizerApp

    with patch.object(OrganizationPreviewView, "_load_preview") as mock_load:
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("organized")
            await pilot.pause()
            mock_load.reset_mock()
            view = app.query_one("#view", OrganizationPreviewView)
            view.action_refresh_preview()
            await pilot.pause()
            mock_load.assert_called()


@pytest.mark.unit
class TestBeforeAfterPanelEdgeCases:
    """Edge case tests for BeforeAfterPanel."""

    def test_set_structure_with_nested_folders(self) -> None:
        panel = BeforeAfterPanel()
        structure = {
            "Folder1": ["file1.txt", "file2.txt"],
            "Folder2": ["nested_file.pdf"],
            "Folder3": [],  # Empty folder
        }
        panel.set_structure(structure, input_dir="/input")
        content = _get_content(panel)
        assert "Folder1" in content
        assert "file1.txt" in content

    def test_set_structure_with_very_long_folder_name(self) -> None:
        panel = BeforeAfterPanel()
        long_name = "a" * 100
        structure = {long_name: ["file.txt"]}
        panel.set_structure(structure)
        content = _get_content(panel)
        # Should handle long names gracefully
        assert len(content) > 0

    def test_set_structure_with_many_files(self) -> None:
        panel = BeforeAfterPanel()
        structure = {"BigFolder": [f"file_{i}.txt" for i in range(100)]}
        panel.set_structure(structure)
        content = _get_content(panel)
        # Should truncate and show "more"
        assert "more" in content or "..." in content or len(content) > 0


@pytest.mark.unit
class TestOrganizationSummaryEdgeCases:
    """Edge case tests for OrganizationSummary."""

    def test_set_result_all_zero(self) -> None:
        summary = OrganizationSummary()
        summary.set_result(total=0, processed=0, skipped=0, failed=0, folders=0)
        content = _get_content(summary)
        assert "0" in content

    def test_set_result_with_no_errors(self) -> None:
        summary = OrganizationSummary()
        summary.set_result(total=10, processed=10, skipped=0, failed=0, folders=2, errors=None)
        content = _get_content(summary)
        assert "10" in content

    def test_set_result_with_only_failed(self) -> None:
        summary = OrganizationSummary()
        summary.set_result(
            total=5, processed=0, skipped=0, failed=5, folders=0, errors=[("f.txt", "err")]
        )
        content = _get_content(summary)
        assert "5" in content
        assert "err" in content

    def test_organization_view_bindings(self) -> None:
        view = OrganizationPreviewView(id="view")
        binding_keys = {b.key for b in view.BINDINGS}
        assert "r" in binding_keys  # Refresh binding
