"""Targeted gap-filler tests for remaining uncovered lines.

Covers:
- settings_view: _coerce_positive_int bool/error/negative paths, _coerce_non_negative_int bool,
  save_parallel_runtime_settings with coerce-to-None max_workers,
  _record_non_sequential_snapshot guard when already sequential
- file_preview: FileSelectionManager deselect+select_all+selected_files,
  FilePreviewView compose/action_select_all/action_deselect_all/action_toggle_select/_notify_selection/_on_file_highlighted
  show_preview AttributeError exception path
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# settings_view – helper function branch coverage
# ===========================================================================


class TestCoercePositiveIntBranches:
    def test_bool_input_returns_none(self):
        from file_organizer.tui.settings_view import _coerce_positive_int

        assert _coerce_positive_int(True) is None
        assert _coerce_positive_int(False) is None

    def test_unparseable_returns_none(self):
        from file_organizer.tui.settings_view import _coerce_positive_int

        assert _coerce_positive_int("abc") is None
        assert _coerce_positive_int([]) is None

    def test_negative_int_returns_none(self):
        from file_organizer.tui.settings_view import _coerce_positive_int

        assert _coerce_positive_int(-5) is None

    def test_zero_returns_none(self):
        from file_organizer.tui.settings_view import _coerce_positive_int

        assert _coerce_positive_int(0) is None

    def test_no_max_value(self):
        from file_organizer.tui.settings_view import _coerce_positive_int

        assert _coerce_positive_int(99, max_value=None) == 99

    def test_with_max_value_clamps(self):
        from file_organizer.tui.settings_view import _coerce_positive_int

        assert _coerce_positive_int(100, max_value=10) == 10


class TestCoerceNonNegativeIntBranches:
    def test_bool_returns_default(self):
        from file_organizer.tui.settings_view import _coerce_non_negative_int

        assert _coerce_non_negative_int(True, default=5) == 5
        assert _coerce_non_negative_int(False, default=3) == 3

    def test_unparseable_returns_default(self):
        from file_organizer.tui.settings_view import _coerce_non_negative_int

        assert _coerce_non_negative_int("bad", default=2) == 2

    def test_negative_returns_default(self):
        from file_organizer.tui.settings_view import _coerce_non_negative_int

        assert _coerce_non_negative_int(-1, default=4) == 4

    def test_zero_is_valid(self):
        from file_organizer.tui.settings_view import _coerce_non_negative_int

        assert _coerce_non_negative_int(0, default=5) == 0


class TestSaveParallelRuntimeSettingsBranches:
    def test_save_with_invalid_coerced_workers_clears_key(self):
        """When max_workers is present but coerces to None, key should be removed."""
        from file_organizer.config.schema import AppConfig
        from file_organizer.tui.settings_view import (
            ParallelRuntimeSettings,
            save_parallel_runtime_settings,
        )

        mock_manager = MagicMock()
        config = AppConfig()
        config.parallel = {"max_workers": 5, "prefetch_depth": 1}
        mock_manager.load.return_value = config

        # Pass a settings with max_workers=-1 (won't coerce, but we need to pass the
        # dataclass as-is; simulate by patching _coerce_positive_int to return None)
        settings = ParallelRuntimeSettings(max_workers=5, prefetch_depth=1)
        with patch("file_organizer.tui.settings_view._coerce_positive_int", return_value=None):
            save_parallel_runtime_settings(settings, manager=mock_manager)

        # max_workers key should be removed since coerce returned None
        assert "max_workers" not in (config.parallel or {})


class TestRecordNonSequentialSnapshotGuard:
    def test_no_snapshot_when_already_sequential(self):
        """_record_non_sequential_snapshot should not update snapshot if currently sequential."""
        from file_organizer.tui.settings_view import SettingsView

        view = SettingsView()
        view._max_workers = 1
        view._prefetch_depth = 0
        view._last_non_sequential_workers = 99
        view._last_non_sequential_prefetch_depth = 99
        view._record_non_sequential_snapshot()
        # Sequential mode → snapshot should NOT be overwritten
        assert view._last_non_sequential_workers == 99
        assert view._last_non_sequential_prefetch_depth == 99


# ===========================================================================
# file_preview – FileSelectionManager remaining branches
# ===========================================================================


class TestFileSelectionManagerRemainingBranches:
    def test_toggle_deselects_already_selected(self):
        from file_organizer.tui.file_preview import FileSelectionManager

        mgr = FileSelectionManager()
        p = Path("/tmp/file.txt")
        mgr._selected.add(p)
        result = mgr.toggle(p)
        assert result is False
        assert p not in mgr._selected

    def test_select_all_adds_paths(self):
        from file_organizer.tui.file_preview import FileSelectionManager

        mgr = FileSelectionManager()
        paths = {Path("/tmp/a.txt"), Path("/tmp/b.txt")}
        mgr.select_all(paths)
        assert mgr.count == 2

    def test_selected_files_returns_copy(self):
        from file_organizer.tui.file_preview import FileSelectionManager

        mgr = FileSelectionManager()
        p = Path("/tmp/x.txt")
        mgr._selected.add(p)
        result = mgr.selected_files
        assert p in result
        result.discard(p)
        assert p in mgr._selected  # original not modified


# ===========================================================================
# file_preview – FilePreviewPanel show_preview exception path
# ===========================================================================


class TestShowPreviewExceptionPath:
    def test_show_preview_swallows_attribute_error(self, tmp_path):
        """When app.call_from_thread raises AttributeError, show_preview should not raise."""
        from file_organizer.tui.file_preview import FilePreviewPanel

        panel = FilePreviewPanel()
        panel.update = MagicMock()
        txt = tmp_path / "hello.txt"
        txt.write_text("content")
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = AttributeError("not mounted")
        with patch.object(type(panel), "app", new_callable=PropertyMock, return_value=mock_app):
            # Should not raise
            FilePreviewPanel.show_preview.__wrapped__(panel, txt)


# ===========================================================================
# file_preview – FilePreviewView compose/actions coverage
# ===========================================================================


class TestFilePreviewViewActions:
    def _make_view(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewView

        view = FilePreviewView(tmp_path)
        view._root_path = tmp_path
        return view

    def test_compose_yields_two_widgets(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewView

        view = FilePreviewView(tmp_path)
        result = list(view.compose())
        assert len(result) == 2

    def test_action_toggle_select_selects_current_file(self, tmp_path):
        view = self._make_view(tmp_path)
        f = tmp_path / "file.txt"
        f.write_text("x")
        view._current_path = f
        view._notify_selection = MagicMock()
        view.action_toggle_select()
        assert view.selection.count == 1
        view._notify_selection.assert_called_once()

    def test_action_toggle_select_does_nothing_without_current_path(self, tmp_path):
        view = self._make_view(tmp_path)
        view._current_path = None
        view._notify_selection = MagicMock()
        view.action_toggle_select()
        view._notify_selection.assert_not_called()

    def test_action_select_all(self, tmp_path):
        view = self._make_view(tmp_path)
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        view._notify_selection = MagicMock()
        view.action_select_all()
        assert view.selection.count == 2
        view._notify_selection.assert_called_once()

    def test_action_select_all_oserror(self, tmp_path):
        view = self._make_view(tmp_path)
        view._notify_selection = MagicMock()
        with patch.object(Path, "rglob", side_effect=OSError("no access")):
            view.action_select_all()
        view._notify_selection.assert_not_called()

    def test_action_deselect_all(self, tmp_path):
        view = self._make_view(tmp_path)
        f = tmp_path / "f.txt"
        f.write_text("x")
        view.selection._selected.add(f)
        view._notify_selection = MagicMock()
        view.action_deselect_all()
        assert view.selection.count == 0
        view._notify_selection.assert_called_once()

    def test_notify_selection_no_app(self, tmp_path):
        view = self._make_view(tmp_path)
        view.post_message = MagicMock()
        view._notify_selection()  # Should not raise

    def test_notify_selection_with_app(self, tmp_path):
        view = self._make_view(tmp_path)
        mock_bar = MagicMock()
        mock_app = MagicMock()
        mock_app.query_one.return_value = mock_bar
        view.post_message = MagicMock()
        with patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app):
            view._notify_selection()
        mock_bar.set_status.assert_called_once()


class TestFilePreviewViewOnFileHighlighted:
    def test_on_file_highlighted_sets_path_and_calls_preview(self, tmp_path):
        from file_organizer.tui.file_preview import FileBrowserView, FilePreviewView

        view = FilePreviewView(tmp_path)
        view._root_path = tmp_path
        f = tmp_path / "f.txt"
        f.write_text("x")

        mock_preview_panel = MagicMock()
        view.query_one = MagicMock(return_value=mock_preview_panel)

        # Create mock event
        event = MagicMock(spec=FileBrowserView.FileHighlighted)
        event.path = f

        view._on_file_highlighted(event)
        assert view._current_path == f
        mock_preview_panel.show_preview.assert_called_once_with(f)


# ===========================================================================
# methodology_view – MethodologySelectorPanel missing lines
# ===========================================================================


class TestMethodologySelectorPanel:
    def test_on_mount_calls_render(self):
        from file_organizer.tui.methodology_view import MethodologySelectorPanel

        panel = MethodologySelectorPanel()
        panel.update = MagicMock()
        panel.on_mount()
        panel.update.assert_called_once()

    def test_set_methodology_updates_current(self):
        from file_organizer.tui.methodology_view import MethodologySelectorPanel

        panel = MethodologySelectorPanel()
        panel.update = MagicMock()
        panel.set_methodology("para")
        assert panel._current == "para"
        panel.update.assert_called_once()

    def test_current_methodology_property(self):
        from file_organizer.tui.methodology_view import MethodologySelectorPanel

        panel = MethodologySelectorPanel()
        assert panel.current_methodology == "none"
        panel._current = "jd"
        assert panel.current_methodology == "jd"

    def test_render_selector_highlights_active(self):
        from file_organizer.tui.methodology_view import MethodologySelectorPanel

        panel = MethodologySelectorPanel()
        panel.update = MagicMock()
        panel._current = "jd"
        panel._render_selector()
        rendered = panel.update.call_args[0][0]
        # Active item should have the green marker
        assert "[bold green]>" in rendered
