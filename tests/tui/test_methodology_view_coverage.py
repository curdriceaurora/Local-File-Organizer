"""Coverage tests for file_organizer.tui.methodology_view module.

Targets uncovered branches: MethodologyView action methods that call
query_one and _update_preview, _load_para_preview, _load_jd_preview
worker paths, and _set_status fallback.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from file_organizer.tui.methodology_view import (
    MethodologyPreviewPanel,
    MethodologySelectorPanel,
    MethodologyView,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# MethodologyView - action methods with mocked query_one
# ---------------------------------------------------------------------------


class TestMethodologyViewActions:
    """Test MethodologyView action methods with mocked widget queries."""

    def test_action_set_para(self) -> None:
        view = MethodologyView()
        mock_selector = MagicMock()
        mock_preview = MagicMock()

        def query_one_side_effect(cls):
            if cls is MethodologySelectorPanel:
                return mock_selector
            return mock_preview

        view.query_one = MagicMock(side_effect=query_one_side_effect)
        view._load_para_preview = MagicMock()
        view.action_set_para()

        assert view._methodology == "para"
        mock_selector.set_methodology.assert_called_with("para")

    def test_action_set_jd(self) -> None:
        view = MethodologyView()
        mock_selector = MagicMock()
        mock_preview = MagicMock()

        def query_one_side_effect(cls):
            if cls is MethodologySelectorPanel:
                return mock_selector
            return mock_preview

        view.query_one = MagicMock(side_effect=query_one_side_effect)
        view._load_jd_preview = MagicMock()
        view.action_set_jd()

        assert view._methodology == "jd"
        mock_selector.set_methodology.assert_called_with("jd")

    def test_action_set_none(self) -> None:
        view = MethodologyView()
        mock_selector = MagicMock()
        mock_preview = MagicMock()

        def query_one_side_effect(cls):
            if cls is MethodologySelectorPanel:
                return mock_selector
            return mock_preview

        view.query_one = MagicMock(side_effect=query_one_side_effect)
        view.action_set_none()

        assert view._methodology == "none"
        mock_selector.set_methodology.assert_called_with("none")
        mock_preview.show_none_preview.assert_called_once()

    def test_update_preview_dispatches_none(self) -> None:
        view = MethodologyView()
        view._methodology = "none"
        mock_preview = MagicMock()
        view.query_one = MagicMock(return_value=mock_preview)
        view._update_preview()
        mock_preview.show_none_preview.assert_called_once()

    def test_update_preview_dispatches_para(self) -> None:
        view = MethodologyView()
        view._methodology = "para"
        mock_preview = MagicMock()
        view.query_one = MagicMock(return_value=mock_preview)
        view._load_para_preview = MagicMock()
        view._update_preview()
        mock_preview.show_loading.assert_called_once()
        view._load_para_preview.assert_called_once()

    def test_update_preview_dispatches_jd(self) -> None:
        view = MethodologyView()
        view._methodology = "jd"
        mock_preview = MagicMock()
        view.query_one = MagicMock(return_value=mock_preview)
        view._load_jd_preview = MagicMock()
        view._update_preview()
        mock_preview.show_loading.assert_called_once()
        view._load_jd_preview.assert_called_once()


# ---------------------------------------------------------------------------
# MethodologyView - _load_para_preview worker
# ---------------------------------------------------------------------------


class TestLoadParaPreview:
    """Test _load_para_preview worker thread."""

    def test_para_preview_no_files(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        view = MethodologyView(scan_dir=empty_dir)
        mock_preview = MagicMock()
        view.query_one = MagicMock(return_value=mock_preview)

        mock_mapper = MagicMock()
        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        with (
            patch(
                "file_organizer.methodologies.para.folder_mapper.CategoryFolderMapper",
                return_value=mock_mapper,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            MethodologyView._load_para_preview.__wrapped__(view)

        # Should call show_para_preview with None (no files)
        mock_preview.show_para_preview.assert_called_once_with(None)

    def test_para_preview_with_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f1.touch()
        f2 = tmp_path / "b.py"
        f2.touch()

        view = MethodologyView(scan_dir=tmp_path)
        mock_preview = MagicMock()
        view.query_one = MagicMock(return_value=mock_preview)

        mock_result = SimpleNamespace(target_category=SimpleNamespace(value="Resources"))
        mock_mapper = MagicMock()
        mock_mapper.map_batch.return_value = [mock_result, mock_result]

        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        with (
            patch(
                "file_organizer.methodologies.para.folder_mapper.CategoryFolderMapper",
                return_value=mock_mapper,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            MethodologyView._load_para_preview.__wrapped__(view)

        mock_preview.show_para_preview.assert_called_once_with({"Resources": 2})

    def test_para_preview_with_plain_category(self, tmp_path: Path) -> None:
        """Test when target_category doesn't have .value attribute."""
        f1 = tmp_path / "a.txt"
        f1.touch()

        view = MethodologyView(scan_dir=tmp_path)
        mock_preview = MagicMock()
        view.query_one = MagicMock(return_value=mock_preview)

        mock_result = SimpleNamespace(target_category="Projects")
        mock_mapper = MagicMock()
        mock_mapper.map_batch.return_value = [mock_result]

        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        with (
            patch(
                "file_organizer.methodologies.para.folder_mapper.CategoryFolderMapper",
                return_value=mock_mapper,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            MethodologyView._load_para_preview.__wrapped__(view)

        mock_preview.show_para_preview.assert_called_once_with({"Projects": 1})

    def test_para_preview_exception(self, tmp_path: Path) -> None:
        view = MethodologyView(scan_dir=tmp_path)
        mock_preview = MagicMock()
        view.query_one = MagicMock(return_value=mock_preview)

        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        with (
            patch(
                "file_organizer.methodologies.para.folder_mapper.CategoryFolderMapper",
                side_effect=RuntimeError("import error"),
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            MethodologyView._load_para_preview.__wrapped__(view)

        # Should call show_error
        mock_preview.show_error.assert_called_once_with("import error")


# ---------------------------------------------------------------------------
# MethodologyView - _load_jd_preview worker
# ---------------------------------------------------------------------------


class TestLoadJdPreview:
    """Test _load_jd_preview worker thread."""

    def test_jd_preview_success(self) -> None:
        view = MethodologyView()
        mock_preview = MagicMock()
        view.query_one = MagicMock(return_value=mock_preview)

        mock_config = MagicMock()
        mock_config.scheme.areas = {10: SimpleNamespace(name="Finance")}
        mock_config.scheme.categories = {"10": SimpleNamespace(name="Banking")}

        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        with (
            patch(
                "file_organizer.methodologies.johnny_decimal.config.create_default_config",
                return_value=mock_config,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            MethodologyView._load_jd_preview.__wrapped__(view)

        mock_preview.show_jd_preview.assert_called_once_with(
            {10: "Finance"},
            {"10": "Banking"},
        )

    def test_jd_preview_no_areas(self) -> None:
        view = MethodologyView()
        mock_preview = MagicMock()
        view.query_one = MagicMock(return_value=mock_preview)

        mock_config = MagicMock()
        mock_config.scheme.areas = None
        mock_config.scheme.categories = None

        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        with (
            patch(
                "file_organizer.methodologies.johnny_decimal.config.create_default_config",
                return_value=mock_config,
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            MethodologyView._load_jd_preview.__wrapped__(view)

        mock_preview.show_jd_preview.assert_called_once_with({}, {})

    def test_jd_preview_exception(self) -> None:
        view = MethodologyView()
        mock_preview = MagicMock()
        view.query_one = MagicMock(return_value=mock_preview)

        mock_app = MagicMock()
        mock_app.call_from_thread.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
        with (
            patch(
                "file_organizer.methodologies.johnny_decimal.config.create_default_config",
                side_effect=ImportError("no jd module"),
            ),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app),
        ):
            MethodologyView._load_jd_preview.__wrapped__(view)

        mock_preview.show_error.assert_called_once_with("no jd module")


# ---------------------------------------------------------------------------
# MethodologyView - _set_status
# ---------------------------------------------------------------------------


class TestMethodologyViewSetStatus:
    """Test _set_status helper."""

    def test_set_status_no_app(self) -> None:
        view = MethodologyView()
        view._set_status("test")  # Should not crash

    def test_set_status_with_mocked_app(self) -> None:
        view = MethodologyView()
        mock_bar = MagicMock()
        mock_app = MagicMock()
        mock_app.query_one.return_value = mock_bar
        with patch.object(type(view), "app", new_callable=PropertyMock, return_value=mock_app):
            view._set_status("loaded")


# ---------------------------------------------------------------------------
# MethodologyPreviewPanel - additional JD branches
# ---------------------------------------------------------------------------


class TestMethodologyPreviewPanelJdCoverage:
    """Cover JD preview branches with non-digit category IDs."""

    def test_jd_with_non_digit_category_id(self) -> None:
        """Category ID that is not a digit should be silently skipped."""
        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        areas = {10: "Finance"}
        categories = {"abc": "Non-numeric", "10": "Banking"}
        panel.show_jd_preview(areas, categories)
        rendered = panel.update.call_args[0][0]
        assert "Finance" in rendered
        assert "Banking" not in rendered or "10" in rendered

    def test_jd_category_outside_area_range(self) -> None:
        """Category ID within digits but outside area range."""
        panel = MethodologyPreviewPanel()
        panel.update = MagicMock()
        areas = {10: "Finance"}
        categories = {"25": "Outside Range"}
        panel.show_jd_preview(areas, categories)
        rendered = panel.update.call_args[0][0]
        assert "Finance" in rendered
        # 25 is not in range 10-19 so should not appear under Finance
        assert "Outside Range" not in rendered
