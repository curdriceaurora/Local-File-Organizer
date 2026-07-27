"""Gap-filler coverage tests for TUI modules.

Targets uncovered lines in:
- analytics_view (panel widget methods, compose/on_mount)
- settings_view (action methods, sequential guards, _set_status, _render_text)
- file_preview (show_preview branches, archive/image/pdf/generic previews)
- methodology_view (action_set_*, _update_preview, panel widget methods)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# analytics_view – panel widget method coverage
# ===========================================================================


class TestStorageOverviewPanel:
    def test_set_stats_renders_correctly(self):
        from file_organizer.tui.analytics_view import StorageOverviewPanel

        panel = StorageOverviewPanel()
        panel.update = MagicMock()
        panel.set_stats(
            total_size="5 GB",
            file_count=42,
            dir_count=7,
            organized_size="3 GB",
            saved_size="1 GB",
        )
        rendered = panel.update.call_args[0][0]
        assert "5 GB" in rendered
        assert "42" in rendered
        assert "7" in rendered
        assert "1 GB" in rendered


class TestFileDistributionPanel:
    def test_set_distribution_empty(self):
        from file_organizer.tui.analytics_view import FileDistributionPanel

        panel = FileDistributionPanel()
        panel.update = MagicMock()
        panel.set_distribution({})
        rendered = panel.update.call_args[0][0]
        assert "No data" in rendered

    def test_set_distribution_with_data(self):
        from file_organizer.tui.analytics_view import FileDistributionPanel

        panel = FileDistributionPanel()
        panel.update = MagicMock()
        panel.set_distribution({".txt": 2048, ".py": 4096})
        rendered = panel.update.call_args[0][0]
        assert ".py" in rendered
        assert ".txt" in rendered

    def test_set_distribution_single_type(self):
        """Single type should produce bar of full length (max == value)."""
        from file_organizer.tui.analytics_view import FileDistributionPanel

        panel = FileDistributionPanel()
        panel.update = MagicMock()
        panel.set_distribution({".md": 1000})
        rendered = panel.update.call_args[0][0]
        assert ".md" in rendered


class TestQualityScorePanel:
    def test_set_metrics_renders(self):
        from file_organizer.tui.analytics_view import QualityScorePanel

        panel = QualityScorePanel()
        panel.update = MagicMock()
        panel.set_metrics(grade="A", naming=1.0, structure=0.9, metadata=0.8, categorization=0.7)
        rendered = panel.update.call_args[0][0]
        assert "Grade: [bold]A[/bold]" in rendered
        assert "Naming" in rendered

    def test_set_metrics_zero_scores(self):
        from file_organizer.tui.analytics_view import QualityScorePanel

        panel = QualityScorePanel()
        panel.update = MagicMock()
        panel.set_metrics()
        rendered = panel.update.call_args[0][0]
        assert "?" in rendered


class TestDuplicateStatsPanel:
    def test_set_stats_renders(self):
        from file_organizer.tui.analytics_view import DuplicateStatsPanel

        panel = DuplicateStatsPanel()
        panel.update = MagicMock()
        panel.set_stats(groups=5, space_wasted="200 MB", recoverable="100 MB")
        rendered = panel.update.call_args[0][0]
        assert "5" in rendered
        assert "200 MB" in rendered


class TestAnalyticsViewMountCompose:
    def test_compose_yields_widgets(self):
        """compose() must yield StaticWidgets — test by verifying it's iterable."""
        from file_organizer.tui.analytics_view import AnalyticsView

        view = AnalyticsView(directory="/tmp")  # noqa: test-hardcoded-paths
        result = list(view.compose())
        # Should yield 5 widgets (header + 4 panels)
        assert len(result) == 5

    def test_on_mount_calls_load(self):
        from file_organizer.tui.analytics_view import AnalyticsView

        view = AnalyticsView()
        view._load_analytics = MagicMock()
        view.on_mount()
        view._load_analytics.assert_called_once()


# ===========================================================================
# settings_view – action method coverage (uncovered branches)
# ===========================================================================


class TestSettingsViewActions:
    def _make_view(self, *, max_workers=4, prefetch=2, sequential=False):
        from file_organizer.tui.settings_view import SettingsView

        view = SettingsView()
        view._max_workers = max_workers
        view._prefetch_depth = prefetch
        if sequential:
            view._max_workers = 1
            view._prefetch_depth = 0
        view._last_non_sequential_workers = max_workers
        view._last_non_sequential_prefetch_depth = prefetch
        return view

    # --- workers_up ---

    def test_workers_up_increments(self):
        view = self._make_view(max_workers=2, prefetch=2)
        with (
            patch("file_organizer.tui.settings_view._MAX_WORKERS_CAP", 10),
            patch.object(view, "_refresh_panel"),
            patch.object(view, "_set_status") as mock_status,
        ):
            view.action_workers_up()
        # The success path updates the panel; it must not also post a status.
        mock_status.assert_not_called()
        assert view._max_workers == 3

    def test_workers_up_from_none_starts_at_2(self):
        """When max_workers is None (auto), up should move to 2."""
        view = self._make_view(max_workers=None, prefetch=2)
        with (
            patch("file_organizer.tui.settings_view._MAX_WORKERS_CAP", 10),
            patch.object(view, "_refresh_panel"),
            patch.object(view, "_set_status") as mock_status,
        ):
            view.action_workers_up()
        # The success path updates the panel; it must not also post a status.
        mock_status.assert_not_called()
        assert view._max_workers == 2

    def test_workers_up_blocked_in_sequential(self):
        view = self._make_view(sequential=True)
        with (
            patch.object(view, "_refresh_panel") as mock_refresh,
            patch.object(view, "_set_status") as mock_status,
        ):
            view.action_workers_up()
        mock_status.assert_called_once()
        mock_refresh.assert_not_called()

    # --- workers_down ---

    def test_workers_down_decrements(self):
        view = self._make_view(max_workers=4, prefetch=2)
        with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status") as mock_status:
            view.action_workers_down()
        # The success path updates the panel; it must not also post a status.
        mock_status.assert_not_called()
        assert view._max_workers == 3

    def test_workers_down_to_none_at_minimum(self):
        view = self._make_view(max_workers=1, prefetch=2)
        with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status") as mock_status:
            view.action_workers_down()
        # The success path updates the panel; it must not also post a status.
        mock_status.assert_not_called()
        assert view._max_workers is None

    def test_workers_down_when_already_none(self):
        view = self._make_view(max_workers=None, prefetch=2)
        with (
            patch.object(view, "_refresh_panel") as mock_refresh,
            patch.object(view, "_set_status") as mock_status,
        ):
            view.action_workers_down()
        mock_refresh.assert_called_once()
        # The success path updates the panel; it must not also post a status.
        mock_status.assert_not_called()

    def test_workers_down_blocked_in_sequential(self):
        view = self._make_view(sequential=True)
        with (
            patch.object(view, "_refresh_panel") as mock_refresh,
            patch.object(view, "_set_status") as mock_status,
        ):
            view.action_workers_down()
        mock_status.assert_called_once()
        mock_refresh.assert_not_called()

    # --- prefetch_up ---

    def test_prefetch_up_increments(self):
        view = self._make_view(max_workers=4, prefetch=2)
        with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status") as mock_status:
            view.action_prefetch_up()
        # The success path updates the panel; it must not also post a status.
        mock_status.assert_not_called()
        assert view._prefetch_depth == 3

    def test_prefetch_up_blocked_in_sequential(self):
        view = self._make_view(sequential=True)
        with (
            patch.object(view, "_refresh_panel") as mock_refresh,
            patch.object(view, "_set_status") as mock_status,
        ):
            view.action_prefetch_up()
        mock_status.assert_called_once()
        mock_refresh.assert_not_called()

    # --- prefetch_down ---

    def test_prefetch_down_decrements(self):
        view = self._make_view(max_workers=4, prefetch=3)
        with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status") as mock_status:
            view.action_prefetch_down()
        # The success path updates the panel; it must not also post a status.
        mock_status.assert_not_called()
        assert view._prefetch_depth == 2

    def test_prefetch_down_clamped_at_zero(self):
        view = self._make_view(max_workers=4, prefetch=0)
        with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status") as mock_status:
            view.action_prefetch_down()
        # The success path updates the panel; it must not also post a status.
        mock_status.assert_not_called()
        assert view._prefetch_depth == 0

    def test_prefetch_down_blocked_in_sequential(self):
        view = self._make_view(sequential=True)
        with (
            patch.object(view, "_refresh_panel") as mock_refresh,
            patch.object(view, "_set_status") as mock_status,
        ):
            view.action_prefetch_down()
        mock_status.assert_called_once()
        mock_refresh.assert_not_called()

    # --- toggle_auto_workers ---

    def test_toggle_auto_workers_sets_to_one_when_none(self):
        view = self._make_view(max_workers=None, prefetch=2)
        with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status") as mock_status:
            view.action_toggle_auto_workers()
        # The success path updates the panel; it must not also post a status.
        mock_status.assert_not_called()
        assert view._max_workers == 1

    def test_toggle_auto_workers_sets_to_none_when_explicit(self):
        view = self._make_view(max_workers=4, prefetch=2)
        with patch.object(view, "_refresh_panel"), patch.object(view, "_set_status") as mock_status:
            view.action_toggle_auto_workers()
        # The success path updates the panel; it must not also post a status.
        mock_status.assert_not_called()
        assert view._max_workers is None

    def test_toggle_auto_workers_blocked_in_sequential(self):
        view = self._make_view(sequential=True)
        with (
            patch.object(view, "_refresh_panel") as mock_refresh,
            patch.object(view, "_set_status") as mock_status,
        ):
            view.action_toggle_auto_workers()
        mock_status.assert_called_once()
        mock_refresh.assert_not_called()

    # --- reload with sequential loaded ---

    def test_reload_sequential_settings_skips_snapshot(self):
        from file_organizer.tui.settings_view import ParallelRuntimeSettings

        view = self._make_view(max_workers=4, prefetch=2)
        seq_settings = ParallelRuntimeSettings(max_workers=1, prefetch_depth=0)
        with (
            patch(
                "file_organizer.tui.settings_view.load_parallel_runtime_settings",
                return_value=seq_settings,
            ),
            patch.object(view, "_refresh_panel"),
            patch.object(view, "_set_status"),
        ):
            view.action_reload_settings()
        assert view._max_workers == 1
        assert view._prefetch_depth == 0

    # --- _set_status ---

    def test_set_status_no_app(self):
        from file_organizer.tui.settings_view import SettingsView

        view = SettingsView()
        view._set_status("ok")  # Should not raise

    def test_set_status_with_app(self):
        from file_organizer.tui.settings_view import SettingsView

        view = SettingsView()
        mock_bar = MagicMock()
        mock_app = MagicMock()
        mock_app.query_one.return_value = mock_bar
        with patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app):
            view._set_status("ready")
        mock_bar.set_status.assert_called_once_with("ready")

    # --- _render_text with auto workers ---

    def test_render_text_auto_workers(self):
        from file_organizer.tui.settings_view import SettingsView

        view = SettingsView()
        view._max_workers = None
        view._prefetch_depth = 2
        text = view._render_text()
        assert "auto" in text

    def test_render_text_sequential_on(self):
        from file_organizer.tui.settings_view import SettingsView

        view = SettingsView()
        view._max_workers = 1
        view._prefetch_depth = 0
        text = view._render_text()
        assert "on" in text

    # --- _refresh_panel ---

    def test_refresh_panel_calls_body_update(self):
        from file_organizer.tui.settings_view import SettingsView

        view = SettingsView()
        mock_body = MagicMock()
        view.query_one = MagicMock(return_value=mock_body)
        view._refresh_panel()
        mock_body.update.assert_called_once()

    # --- compose / on_mount ---

    def test_compose_yields_static_and_directory_inputs(self):
        from textual.widgets import Input, Static

        from file_organizer.tui.settings_view import SettingsView

        view = SettingsView()
        result = list(view.compose())
        assert len(result) == 3
        assert isinstance(result[0], Static)
        assert isinstance(result[1], Input)
        assert isinstance(result[2], Input)

    def test_on_mount_calls_reload(self):
        from file_organizer.tui.settings_view import SettingsView

        view = SettingsView()
        view.action_reload_settings = MagicMock()
        view.on_mount()
        view.action_reload_settings.assert_called_once()


# ===========================================================================
# file_preview – FilePreviewPanel.show_preview branches
# ===========================================================================


class TestFilePreviewPanelShowPreview:
    def _make_panel(self):
        from file_organizer.tui.file_preview import FilePreviewPanel

        panel = FilePreviewPanel()
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        panel.update = MagicMock()
        with patch.object(type(panel), "app", new_callable=PropertyMock, return_value=mock_app):
            return panel, mock_app

    def test_show_preview_file_not_found(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        panel = FilePreviewPanel()
        panel.update = MagicMock()
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        missing = tmp_path / "ghost.txt"
        with patch.object(type(panel), "app", new_callable=PropertyMock, return_value=mock_app):
            FilePreviewPanel.show_preview.__wrapped__(panel, missing)
        panel.update.assert_called_once_with("[dim]File not found[/dim]")

    def test_show_preview_text_file(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        panel = FilePreviewPanel()
        panel.update = MagicMock()
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        txt = tmp_path / "hello.txt"
        txt.write_text("line1\nline2\n")
        with patch.object(type(panel), "app", new_callable=PropertyMock, return_value=mock_app):
            FilePreviewPanel.show_preview.__wrapped__(panel, txt)
        panel.update.assert_called_once()
        assert "line1" in panel.update.call_args[0][0]

    def test_show_preview_directory(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        panel = FilePreviewPanel()
        panel.update = MagicMock()
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        subdir = tmp_path / "mydir"
        subdir.mkdir()
        (subdir / "a.txt").write_text("x")
        with patch.object(type(panel), "app", new_callable=PropertyMock, return_value=mock_app):
            FilePreviewPanel.show_preview.__wrapped__(panel, subdir)
        panel.update.assert_called_once()
        assert "mydir" in panel.update.call_args[0][0]

    def test_show_preview_image_file(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        panel = FilePreviewPanel()
        panel.update = MagicMock()
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        img_path = tmp_path / "photo.jpg"
        img_path.write_bytes(b"\x00")
        with patch.object(type(panel), "app", new_callable=PropertyMock, return_value=mock_app):
            FilePreviewPanel.show_preview.__wrapped__(panel, img_path)
        panel.update.assert_called_once()

    def test_show_preview_pdf_file(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        panel = FilePreviewPanel()
        panel.update = MagicMock()
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF")
        with patch.object(type(panel), "app", new_callable=PropertyMock, return_value=mock_app):
            FilePreviewPanel.show_preview.__wrapped__(panel, pdf)
        panel.update.assert_called_once()

    def test_show_preview_archive_file(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        panel = FilePreviewPanel()
        panel.update = MagicMock()
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        arc = tmp_path / "data.zip"
        arc.write_bytes(b"PK")
        with patch.object(type(panel), "app", new_callable=PropertyMock, return_value=mock_app):
            FilePreviewPanel.show_preview.__wrapped__(panel, arc)
        panel.update.assert_called_once()

    def test_show_preview_generic_file(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        panel = FilePreviewPanel()
        panel.update = MagicMock()
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        unknown = tmp_path / "data.bin"
        unknown.write_bytes(b"\xde\xad\xbe\xef")
        with patch.object(type(panel), "app", new_callable=PropertyMock, return_value=mock_app):
            FilePreviewPanel.show_preview.__wrapped__(panel, unknown)
        panel.update.assert_called_once()


class TestFilePreviewStaticMethods:
    def test_preview_text_read_error(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        path = tmp_path / "f.txt"
        path.write_text("x")
        with patch.object(Path, "read_text", side_effect=OSError("perm denied")):
            result = FilePreviewPanel._preview_text(path)
        assert "Cannot read file" in result

    def test_preview_text_truncation(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        path = tmp_path / "big.txt"
        path.write_text("\n".join(f"line{i}" for i in range(200)))
        result = FilePreviewPanel._preview_text(path, max_lines=100)
        assert "100 of" in result

    def test_preview_image_success(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        path = tmp_path / "img.jpg"
        path.write_bytes(b"\x00")
        # Result will be either metadata (PIL available) or an error string
        result = FilePreviewPanel._preview_image(path)
        assert "Image" in result

    def test_preview_image_error(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        path = tmp_path / "corrupt.jpg"
        path.write_bytes(b"not_an_image")
        result = FilePreviewPanel._preview_image(path)
        # Should return error or metadata string (PIL may fail gracefully)
        assert "Image" in result

    def test_preview_pdf_error(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        path = tmp_path / "bad.pdf"
        path.write_bytes(b"not_pdf")
        result = FilePreviewPanel._preview_pdf(path)
        assert "PDF" in result

    def test_preview_archive_empty(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        path = tmp_path / "empty.zip"
        path.write_bytes(b"PK")
        with patch(
            "file_organizer.utils.file_readers.read_file",
            return_value="",
        ):
            result = FilePreviewPanel._preview_archive(path)
        assert "Archive" in result

    def test_preview_archive_with_content(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        path = tmp_path / "data.zip"
        path.write_bytes(b"PK")
        with patch(
            "file_organizer.utils.file_readers.read_file",
            return_value="Archive Contents\n\nfile.txt",
        ):
            result = FilePreviewPanel._preview_archive(path)
        assert "file.txt" in result
        assert "Archive" in result

    def test_preview_archive_exception(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        path = tmp_path / "broken.zip"
        path.write_bytes(b"PK")
        with patch(
            "file_organizer.utils.file_readers.read_file",
            side_effect=RuntimeError("bad"),
        ):
            result = FilePreviewPanel._preview_archive(path)
        assert "Archive" in result

    def test_preview_directory_error(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        path = tmp_path / "locked"
        path.mkdir()
        with patch.object(Path, "iterdir", side_effect=OSError("permission")):
            result = FilePreviewPanel._preview_directory(path)
        assert "Cannot list" in result

    def test_preview_generic_stat(self, tmp_path):
        from file_organizer.tui.file_preview import FilePreviewPanel

        path = tmp_path / "data.bin"
        path.write_bytes(b"\xde\xad")
        result = FilePreviewPanel._preview_generic(path)
        assert "data.bin" in result


# ===========================================================================
# methodology_view – action and _update_preview coverage
# ===========================================================================


class TestMethodologyViewActions:
    def _make_view(self):
        from file_organizer.tui.methodology_view import (
            MethodologyPreviewPanel,
            MethodologySelectorPanel,
            MethodologyView,
        )

        view = MethodologyView()
        view._methodology = "none"
        mock_selector = MagicMock()
        mock_preview = MagicMock()

        def _query_one(panel_type):
            mapping = {
                MethodologySelectorPanel: mock_selector,
                MethodologyPreviewPanel: mock_preview,
            }
            return mapping[panel_type]

        view.query_one = MagicMock(side_effect=_query_one)
        return view, mock_selector, mock_preview

    def test_action_set_para(self):
        view, selector, preview = self._make_view()
        view._load_para_preview = MagicMock()
        view._set_status = MagicMock()
        view.action_set_para()
        assert view._methodology == "para"
        selector.set_methodology.assert_called_once_with("para")

    def test_action_set_jd(self):
        view, selector, preview = self._make_view()
        view._load_jd_preview = MagicMock()
        view._set_status = MagicMock()
        view.action_set_jd()
        assert view._methodology == "jd"
        selector.set_methodology.assert_called_once_with("jd")

    def test_action_set_none(self):
        view, selector, preview = self._make_view()
        view.action_set_none()
        assert view._methodology == "none"
        selector.set_methodology.assert_called_once_with("none")

    def test_update_preview_none(self):
        view, selector, preview = self._make_view()
        view._methodology = "none"
        view._update_preview()
        preview.show_none_preview.assert_called_once()

    def test_update_preview_para(self):
        view, selector, preview = self._make_view()
        view._methodology = "para"
        view._load_para_preview = MagicMock()
        view._update_preview()
        preview.show_loading.assert_called_once()
        view._load_para_preview.assert_called_once()

    def test_update_preview_jd(self):
        view, selector, preview = self._make_view()
        view._methodology = "jd"
        view._load_jd_preview = MagicMock()
        view._update_preview()
        preview.show_loading.assert_called_once()
        view._load_jd_preview.assert_called_once()

    def test_action_migrate_calls_set_status(self):
        view, _, _ = self._make_view()
        view._set_status = MagicMock()
        view.action_migrate()
        view._set_status.assert_called_once()

    def test_set_status_no_app(self):
        from file_organizer.tui.methodology_view import MethodologyView

        view = MethodologyView()
        view._set_status("ok")  # Should not raise

    def test_set_status_with_app(self):
        from file_organizer.tui.methodology_view import MethodologyView

        view = MethodologyView()
        mock_bar = MagicMock()
        mock_app = MagicMock()
        mock_app.query_one.return_value = mock_bar
        with patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app):
            view._set_status("migrating")
        mock_bar.set_status.assert_called_once_with("migrating")


class TestMethodologyPreviewPanel:
    def test_show_none_preview(self):
        from file_organizer.tui.methodology_view import MethodologyPreviewPanel

        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        panel.show_none_preview()
        panel.update.assert_called_once()

    def test_show_para_preview_with_distribution(self):
        from file_organizer.tui.methodology_view import MethodologyPreviewPanel

        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        distribution = {"Projects": 5, "Areas": 3, "Resources": 2, "Archive": 1}
        panel.show_para_preview(distribution)
        rendered = panel.update.call_args[0][0]
        assert "Projects" in rendered

    def test_show_para_preview_empty(self):
        from file_organizer.tui.methodology_view import MethodologyPreviewPanel

        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        panel.show_para_preview(None)
        rendered = panel.update.call_args[0][0]
        assert "No files" in rendered

    def test_show_jd_preview_with_areas(self):
        from file_organizer.tui.methodology_view import MethodologyPreviewPanel

        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        areas = {10: "Finance", 20: "Health"}
        categories = {"11": "Invoices", "12": "Expenses"}
        panel.show_jd_preview(areas, categories)
        rendered = panel.update.call_args[0][0]
        assert "Finance" in rendered

    def test_show_jd_preview_empty(self):
        from file_organizer.tui.methodology_view import MethodologyPreviewPanel

        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        panel.show_jd_preview(None)
        rendered = panel.update.call_args[0][0]
        assert "No scheme" in rendered

    def test_show_loading(self):
        from file_organizer.tui.methodology_view import MethodologyPreviewPanel

        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        panel.show_loading()
        panel.update.assert_called_once()

    def test_show_error(self):
        from file_organizer.tui.methodology_view import MethodologyPreviewPanel

        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        panel.show_error("something broke")
        rendered = panel.update.call_args[0][0]
        assert "something broke" in rendered
