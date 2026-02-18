"""Tests for TUI methodology selector view."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from file_organizer.tui.methodology_view import (
    MethodologyPreviewPanel,
    MethodologySelectorPanel,
    MethodologyView,
)


def _get_content(widget: object) -> str:
    """Extract the text content from a Static widget."""
    return str(getattr(widget, "_Static__content", ""))


class TestMethodologySelectorPanel:
    """Unit tests for MethodologySelectorPanel."""

    def test_default_methodology(self) -> None:
        panel = MethodologySelectorPanel()
        assert panel._current == "none"

    def test_set_methodology(self) -> None:
        panel = MethodologySelectorPanel()
        panel.set_methodology("para")
        assert panel._current == "para"

    def test_set_jd(self) -> None:
        panel = MethodologySelectorPanel()
        panel.set_methodology("jd")
        assert panel._current == "jd"


class TestMethodologyPreviewPanel:
    """Unit tests for MethodologyPreviewPanel."""

    def test_show_none_preview(self) -> None:
        panel = MethodologyPreviewPanel()
        panel.show_none_preview()
        content = _get_content(panel)
        assert "No Methodology" in content

    def test_show_para_preview_with_data(self) -> None:
        panel = MethodologyPreviewPanel()
        panel.show_para_preview({"Projects": 5, "Areas": 3, "Resources": 8, "Archive": 2})
        content = _get_content(panel)
        assert "PARA" in content
        assert "Projects" in content

    def test_show_para_preview_empty(self) -> None:
        panel = MethodologyPreviewPanel()
        panel.show_para_preview(None)
        content = _get_content(panel)
        assert "No files" in content

    def test_show_jd_preview_with_data(self) -> None:
        panel = MethodologyPreviewPanel()
        panel.show_jd_preview(
            areas={10: "Finance", 20: "Admin"},
            categories={"11": "Invoices", "12": "Receipts", "21": "HR"},
        )
        content = _get_content(panel)
        assert "Johnny Decimal" in content
        assert "Finance" in content

    def test_show_jd_preview_empty(self) -> None:
        panel = MethodologyPreviewPanel()
        panel.show_jd_preview(None, None)
        content = _get_content(panel)
        assert "No scheme" in content

    def test_show_loading(self) -> None:
        panel = MethodologyPreviewPanel()
        panel.show_loading()
        assert "Loading" in _get_content(panel)

    def test_show_error(self) -> None:
        panel = MethodologyPreviewPanel()
        panel.show_error("Connection failed")
        assert "Connection failed" in _get_content(panel)


class TestMethodologyView:
    """Unit tests for MethodologyView."""

    def test_default_methodology(self) -> None:
        view = MethodologyView(id="view")
        assert view._methodology == "none"

    def test_scan_dir(self) -> None:
        view = MethodologyView(scan_dir="/tmp/test", id="view")
        assert str(view._scan_dir) == "/tmp/test"


@pytest.mark.asyncio
async def test_methodology_view_mounts() -> None:
    """MethodologyView should mount with selector and preview panels."""
    from file_organizer.tui.app import FileOrganizerApp

    app = FileOrganizerApp()
    async with app.run_test() as pilot:
        await app.action_switch_view("methodology")
        await pilot.pause()
        view = app.query_one("#view", MethodologyView)
        assert view is not None
        assert view.query_one(MethodologySelectorPanel) is not None
        assert view.query_one(MethodologyPreviewPanel) is not None
        await pilot.press("q")


@pytest.mark.asyncio
async def test_switch_to_para() -> None:
    """Pressing 'p' should switch to PARA methodology."""
    from file_organizer.tui.app import FileOrganizerApp

    with patch.object(MethodologyView, "_load_para_preview"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("methodology")
            await pilot.pause()
            view = app.query_one("#view", MethodologyView)
            view.action_set_para()
            await pilot.pause()
            assert view._methodology == "para"


@pytest.mark.asyncio
async def test_switch_to_jd() -> None:
    """Pressing 'j' should switch to Johnny Decimal."""
    from file_organizer.tui.app import FileOrganizerApp

    with patch.object(MethodologyView, "_load_jd_preview"):
        app = FileOrganizerApp()
        async with app.run_test() as pilot:
            await app.action_switch_view("methodology")
            await pilot.pause()
            view = app.query_one("#view", MethodologyView)
            view.action_set_jd()
            await pilot.pause()
            assert view._methodology == "jd"
