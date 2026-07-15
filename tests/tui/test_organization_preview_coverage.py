"""Coverage tests for file_organizer.tui.organization_preview module.

Targets uncovered branches: OrganizationPreviewView._load_preview worker,
action_refresh_preview, action_confirm, action_cancel, _set_status.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, call, patch

import pytest

from file_organizer.tui.organization_preview import (
    BeforeAfterPanel,
    OrganizationPreviewView,
    OrganizationSummary,
)
from file_organizer.tui.settings_view import ParallelRuntimeSettings

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# BeforeAfterPanel edge cases
# ---------------------------------------------------------------------------


class TestBeforeAfterPanelCoverage:
    """Additional coverage for BeforeAfterPanel."""

    def test_set_structure_no_input_dir(self) -> None:
        """Test without input_dir — uses filename directly."""
        panel = BeforeAfterPanel()
        panel.update = MagicMock()
        structure = {"Docs": ["readme.md"]}
        panel.set_structure(structure, input_dir="")
        rendered = panel.update.call_args[0][0]
        assert "readme.md" in rendered
        # Without input_dir, no prefix path
        assert "readme.md  [dim]->[/dim]  Docs/readme.md" in rendered

    def test_set_structure_exactly_20_files(self) -> None:
        """Test with exactly 20 files — no truncation."""
        panel = BeforeAfterPanel()
        panel.update = MagicMock()
        files = [f"file{i}.txt" for i in range(20)]
        structure = {"Docs": files}
        panel.set_structure(structure)
        rendered = panel.update.call_args[0][0]
        assert "... and" not in rendered

    def test_set_structure_21_files_truncated(self) -> None:
        """Test with 21 files — shows truncation."""
        panel = BeforeAfterPanel()
        panel.update = MagicMock()
        files = [f"file{i}.txt" for i in range(21)]
        structure = {"Docs": files}
        panel.set_structure(structure)
        rendered = panel.update.call_args[0][0]
        assert "... and 1 more" in rendered


# ---------------------------------------------------------------------------
# OrganizationSummary edge cases
# ---------------------------------------------------------------------------


class TestOrganizationSummaryCoverage:
    """Additional coverage for OrganizationSummary."""

    def test_errors_exactly_5(self) -> None:
        """Test with exactly 5 errors — no truncation."""
        panel = OrganizationSummary()
        panel.update = MagicMock()
        errors = [(f"file{i}.txt", f"Error {i}") for i in range(5)]
        panel.set_result(failed=5, errors=errors)
        rendered = panel.update.call_args[0][0]
        assert "Errors:" in rendered
        assert "... and" not in rendered

    def test_errors_empty_list(self) -> None:
        """Test with empty error list (not None) — no Errors section."""
        panel = OrganizationSummary()
        panel.update = MagicMock()
        panel.set_result(failed=0, errors=[])
        rendered = panel.update.call_args[0][0]
        assert "Errors:" not in rendered


# ---------------------------------------------------------------------------
# OrganizationPreviewView - _load_preview worker
# ---------------------------------------------------------------------------


class TestOrganizationPreviewViewLoadPreview:
    """Test _load_preview worker thread paths."""

    def test_load_preview_success(self) -> None:
        view = OrganizationPreviewView()
        before_after_panel = MagicMock()
        summary_panel = MagicMock()

        def _query_side_effect(panel_type):
            mapping = {
                BeforeAfterPanel: before_after_panel,
                OrganizationSummary: summary_panel,
            }
            return mapping[panel_type]

        view.query_one = MagicMock(side_effect=_query_side_effect)

        mock_result = SimpleNamespace(
            organized_structure={"Docs": ["a.pdf"]},
            total_files=10,
            processed_files=8,
            skipped_files=1,
            failed_files=1,
            errors=[("bad.txt", "corrupt")],
        )
        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = mock_result

        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        with (
            patch(
                "file_organizer.tui.organization_preview.load_parallel_runtime_settings",
                return_value=ParallelRuntimeSettings(max_workers=2, prefetch_depth=1),
            ),
            patch(
                "file_organizer.core.organizer.FileOrganizer",
                return_value=mock_organizer,
            ) as mock_org_cls,
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            OrganizationPreviewView._load_preview.__wrapped__(view)

        mock_org_cls.assert_called_once_with(
            dry_run=True,
            parallel_workers=2,
            prefetch_depth=1,
        )
        assert mock_app.call_from_thread.call_count == 3
        before_after_panel.set_structure.assert_called_once_with(
            {"Docs": ["a.pdf"]},
            str(view._input_dir),
        )
        summary_panel.set_result.assert_called_once_with(
            total=10,
            processed=8,
            skipped=1,
            failed=1,
            folders=1,
            errors=[("bad.txt", "corrupt")],
        )
        assert mock_app.call_from_thread.call_args_list[-1] == call(
            view._set_status,
            "Preview loaded",
        )

    def test_load_preview_exception(self) -> None:
        view = OrganizationPreviewView()
        before_after_panel = MagicMock()
        summary_panel = MagicMock()

        def _query_side_effect(panel_type):
            mapping = {
                BeforeAfterPanel: before_after_panel,
                OrganizationSummary: summary_panel,
            }
            return mapping[panel_type]

        view.query_one = MagicMock(side_effect=_query_side_effect)

        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        with (
            patch(
                "file_organizer.tui.organization_preview.load_parallel_runtime_settings",
                return_value=ParallelRuntimeSettings(max_workers=None, prefetch_depth=2),
            ),
            patch(
                "file_organizer.core.organizer.FileOrganizer",
                side_effect=RuntimeError("model not found"),
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            OrganizationPreviewView._load_preview.__wrapped__(view)

        assert mock_app.call_from_thread.call_count == 2
        before_after_panel.update.assert_called_once_with(
            "[red]Models unavailable:[/red] model not found\n\n"
            "[dim]Ensure Ollama is running with required models.[/dim]"
        )
        summary_panel.update.assert_called_once_with("[dim]No data available.[/dim]")

    def test_action_refresh_preview(self) -> None:
        view = OrganizationPreviewView()
        mock_panel = MagicMock()
        view.query_one = MagicMock(return_value=mock_panel)
        view._load_preview = MagicMock()
        view.action_refresh_preview()
        view._load_preview.assert_called_once()

    def test_action_confirm_starts_apply_worker(self) -> None:
        view = OrganizationPreviewView()
        mock_panel = MagicMock()
        view.query_one = MagicMock(return_value=mock_panel)
        view._set_status = MagicMock()
        view._apply_organization = MagicMock()

        view.action_confirm()

        assert mock_panel.update.call_args_list == [
            call("[dim]Applying organization...[/dim]"),
            call("[dim]Working...[/dim]"),
        ]
        view._set_status.assert_called_once_with("Applying organization...")
        view._apply_organization.assert_called_once()
        assert view._is_applying is True

    def test_action_confirm_ignores_duplicate_apply(self) -> None:
        view = OrganizationPreviewView()
        view._is_applying = True
        view.query_one = MagicMock()
        view._set_status = MagicMock()
        view._apply_organization = MagicMock()

        view.action_confirm()

        view.query_one.assert_not_called()
        view._set_status.assert_called_once_with("Organization is already applying...")
        view._apply_organization.assert_not_called()

    def test_apply_organization_success_uses_real_organizer(self, tmp_path) -> None:
        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        view = OrganizationPreviewView(input_dir=input_dir, output_dir=output_dir)
        mock_result = SimpleNamespace(
            organized_structure={"Docs": ["a.pdf"]},
            total_files=1,
            processed_files=1,
            skipped_files=0,
            failed_files=0,
            errors=[],
        )
        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = mock_result
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        view._handle_apply_success = MagicMock()

        with (
            patch(
                "file_organizer.tui.organization_preview.load_parallel_runtime_settings",
                return_value=ParallelRuntimeSettings(max_workers=3, prefetch_depth=4),
            ),
            patch(
                "file_organizer.core.organizer.FileOrganizer",
                return_value=mock_organizer,
            ) as mock_org_cls,
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            OrganizationPreviewView._apply_organization.__wrapped__(view)

        mock_org_cls.assert_called_once_with(
            dry_run=False,
            parallel_workers=3,
            prefetch_depth=4,
        )
        mock_organizer.organize.assert_called_once_with(
            input_path=view._input_dir,
            output_path=view._output_dir,
        )
        view._handle_apply_success.assert_called_once_with(mock_result)

    def test_handle_apply_success_switches_to_history(self, tmp_path) -> None:
        input_dir = tmp_path / "in"
        view = OrganizationPreviewView(input_dir=input_dir)
        view._is_applying = True
        before_after_panel = MagicMock()
        summary_panel = MagicMock()

        class AwaitableSwitch:
            def __await__(self):
                if False:
                    yield None
                return None

        def _query_side_effect(panel_type):
            mapping = {
                BeforeAfterPanel: before_after_panel,
                OrganizationSummary: summary_panel,
            }
            return mapping[panel_type]

        view.query_one = MagicMock(side_effect=_query_side_effect)
        view._set_status = MagicMock()
        mock_app = MagicMock()
        mock_app.action_switch_view = MagicMock(return_value=AwaitableSwitch())
        mock_app.run_worker = MagicMock()
        mock_result = SimpleNamespace(
            organized_structure={"Docs": ["a.pdf"]},
            total_files=1,
            processed_files=1,
            skipped_files=0,
            failed_files=0,
            errors=[],
        )

        with patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app):
            view._handle_apply_success(mock_result)

        assert view._is_applying is False
        before_after_panel.set_structure.assert_called_once_with(
            {"Docs": ["a.pdf"]}, str(input_dir)
        )
        summary_panel.set_result.assert_called_once_with(
            total=1,
            processed=1,
            skipped=0,
            failed=0,
            folders=1,
            errors=[],
        )
        view._set_status.assert_called_once_with("Organization applied. Opening history.")
        mock_app.action_switch_view.assert_called_once_with("history")
        mock_app.run_worker.assert_called_once()

    def test_handle_apply_success_without_switch_view_action(self, tmp_path) -> None:
        """An app without action_switch_view still applies the result cleanly."""
        input_dir = tmp_path / "in"
        view = OrganizationPreviewView(input_dir=input_dir)
        view._is_applying = True
        before_after_panel = MagicMock()
        summary_panel = MagicMock()

        def _query_side_effect(panel_type):
            mapping = {
                BeforeAfterPanel: before_after_panel,
                OrganizationSummary: summary_panel,
            }
            return mapping[panel_type]

        view.query_one = MagicMock(side_effect=_query_side_effect)
        view._set_status = MagicMock()
        mock_app = MagicMock()
        del mock_app.action_switch_view
        mock_result = SimpleNamespace(
            organized_structure={"Docs": ["a.pdf"]},
            total_files=1,
            processed_files=1,
            skipped_files=0,
            failed_files=0,
            errors=[],
        )

        with patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app):
            view._handle_apply_success(mock_result)

        assert view._is_applying is False
        before_after_panel.set_structure.assert_called_once_with(
            {"Docs": ["a.pdf"]}, str(input_dir)
        )
        view._set_status.assert_called_once_with("Organization applied. Opening history.")
        mock_app.run_worker.assert_not_called()

    def test_apply_organization_exception_shows_apply_error(self) -> None:
        view = OrganizationPreviewView()
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        view._handle_apply_error = MagicMock()

        with (
            patch(
                "file_organizer.tui.organization_preview.load_parallel_runtime_settings",
                return_value=ParallelRuntimeSettings(max_workers=1, prefetch_depth=1),
            ),
            patch(
                "file_organizer.core.organizer.FileOrganizer",
                side_effect=RuntimeError("model offline"),
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            OrganizationPreviewView._apply_organization.__wrapped__(view)

        view._handle_apply_error.assert_called_once()
        assert isinstance(view._handle_apply_error.call_args.args[0], RuntimeError)

    def test_handle_apply_error_updates_panels_and_status(self) -> None:
        view = OrganizationPreviewView()
        view._is_applying = True
        before_after_panel = MagicMock()
        summary_panel = MagicMock()

        def _query_side_effect(panel_type):
            mapping = {
                BeforeAfterPanel: before_after_panel,
                OrganizationSummary: summary_panel,
            }
            return mapping[panel_type]

        view.query_one = MagicMock(side_effect=_query_side_effect)
        view._set_status = MagicMock()

        view._handle_apply_error(RuntimeError("disk full"))

        assert view._is_applying is False
        before_after_panel.update.assert_called_once_with(
            "[red]Apply failed:[/red] disk full\n\n"
            "[dim]Some files may have been changed. Check History before retrying.[/dim]"
        )
        summary_panel.update.assert_called_once_with("[dim]No data available.[/dim]")
        view._set_status.assert_called_once_with("Apply failed")

    def test_set_status_no_app(self) -> None:
        view = OrganizationPreviewView()
        view._set_status("test")  # Should not crash

    def test_set_status_with_app(self) -> None:
        view = OrganizationPreviewView()
        mock_bar = MagicMock()
        mock_app = MagicMock()
        mock_app.query_one.return_value = mock_bar
        with patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app):
            view._set_status("loaded")
