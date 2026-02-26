"""Unit tests for web files_routes helpers and route handlers.

Tests internal helpers (_build_breadcrumbs, _list_tree_nodes,
_collect_entries, _build_file_results_context) and route handlers
using mocked templates/settings.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.exceptions import ApiError
from file_organizer.web.files_routes import (
    _build_breadcrumbs,
    _build_file_results_context,
    _collect_entries,
    _list_tree_nodes,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tree(tmp_path):
    """Create a sample file tree for testing."""
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "dir_b").mkdir()
    (tmp_path / ".hidden_dir").mkdir()
    (tmp_path / "file1.txt").write_text("hello")
    (tmp_path / "file2.png").write_bytes(b"\x89PNG")
    (tmp_path / ".hidden_file").write_text("secret")
    (tmp_path / "dir_a" / "nested.txt").write_text("nested")
    return tmp_path


@pytest.fixture()
def settings(tree):
    """Return an ApiSettings mock pointing at the tree."""
    s = MagicMock(spec=ApiSettings)
    s.allowed_paths = [str(tree)]
    return s


# ---------------------------------------------------------------------------
# _build_breadcrumbs
# ---------------------------------------------------------------------------


class TestBuildBreadcrumbs:
    """Test breadcrumb generation."""

    def test_root_path(self, tree):
        crumbs = _build_breadcrumbs(tree, [tree])
        assert len(crumbs) == 1
        assert crumbs[0]["path"] == str(tree)

    def test_nested_path(self, tree):
        nested = tree / "dir_a"
        crumbs = _build_breadcrumbs(nested, [tree])
        assert len(crumbs) == 2
        assert crumbs[0]["path"] == str(tree)
        assert crumbs[1]["label"] == "dir_a"

    def test_deeply_nested(self, tree):
        deep = tree / "dir_a"
        deep_child = deep / "sub"
        deep_child.mkdir()
        crumbs = _build_breadcrumbs(deep_child, [tree])
        assert len(crumbs) == 3

    def test_path_outside_roots(self, tree, tmp_path):
        other = tmp_path / "other"
        other.mkdir()
        # Should return at least the closest root
        crumbs = _build_breadcrumbs(other, [tree])
        assert len(crumbs) >= 1


# ---------------------------------------------------------------------------
# _list_tree_nodes
# ---------------------------------------------------------------------------


class TestListTreeNodes:
    """Test sidebar tree node listing."""

    def test_excludes_hidden(self, tree):
        nodes = _list_tree_nodes(tree, include_hidden=False)
        names = [n["name"] for n in nodes]
        assert "dir_a" in names
        assert "dir_b" in names
        assert ".hidden_dir" not in names

    def test_includes_hidden(self, tree):
        nodes = _list_tree_nodes(tree, include_hidden=True)
        names = [n["name"] for n in nodes]
        assert ".hidden_dir" in names

    def test_only_directories(self, tree):
        nodes = _list_tree_nodes(tree, include_hidden=False)
        # Should not include files
        names = [n["name"] for n in nodes]
        assert "file1.txt" not in names

    def test_sorted_by_name(self, tree):
        nodes = _list_tree_nodes(tree, include_hidden=False)
        names = [n["name"] for n in nodes]
        assert names == sorted(names, key=str.lower)

    def test_nonexistent_path(self, tmp_path):
        nodes = _list_tree_nodes(tmp_path / "nope", include_hidden=False)
        assert nodes == []

    def test_node_has_required_keys(self, tree):
        nodes = _list_tree_nodes(tree, include_hidden=False)
        for node in nodes:
            assert "id" in node
            assert "name" in node
            assert "path" in node
            assert "path_param" in node
            assert "has_children" in node


# ---------------------------------------------------------------------------
# _collect_entries
# ---------------------------------------------------------------------------


class TestCollectEntries:
    """Test directory entry collection, filtering, and sorting."""

    def test_basic_listing(self, tree):
        entries, total = _collect_entries(
            tree, query=None, file_type=None,
            sort_by="name", sort_order="asc",
            include_hidden=False, limit=100,
        )
        # 2 dirs + 2 visible files
        assert total == 4
        assert len(entries) == 4

    def test_query_filter(self, tree):
        entries, total = _collect_entries(
            tree, query="file1", file_type=None,
            sort_by="name", sort_order="asc",
            include_hidden=False, limit=100,
        )
        file_names = [e["name"] for e in entries if not e["is_dir"]]
        assert "file1.txt" in file_names
        assert "file2.png" not in file_names

    def test_file_type_filter(self, tree):
        entries, total = _collect_entries(
            tree, query=None, file_type="image",
            sort_by="name", sort_order="asc",
            include_hidden=False, limit=100,
        )
        file_entries = [e for e in entries if not e["is_dir"]]
        assert all("png" in e["name"].lower() or e["kind"] == "image" for e in file_entries)

    def test_include_hidden(self, tree):
        entries, total = _collect_entries(
            tree, query=None, file_type=None,
            sort_by="name", sort_order="asc",
            include_hidden=True, limit=100,
        )
        names = [e["name"] for e in entries]
        assert ".hidden_dir" in names
        assert ".hidden_file" in names

    def test_sort_by_size(self, tree):
        entries, _ = _collect_entries(
            tree, query=None, file_type=None,
            sort_by="size", sort_order="desc",
            include_hidden=False, limit=100,
        )
        assert len(entries) > 0

    def test_sort_by_created(self, tree):
        entries, _ = _collect_entries(
            tree, query=None, file_type=None,
            sort_by="created", sort_order="asc",
            include_hidden=False, limit=100,
        )
        assert len(entries) > 0

    def test_sort_by_type(self, tree):
        entries, _ = _collect_entries(
            tree, query=None, file_type=None,
            sort_by="type", sort_order="asc",
            include_hidden=False, limit=100,
        )
        assert len(entries) > 0

    def test_sort_by_modified(self, tree):
        entries, _ = _collect_entries(
            tree, query=None, file_type=None,
            sort_by="modified", sort_order="desc",
            include_hidden=False, limit=100,
        )
        assert len(entries) > 0

    def test_limit_zero(self, tree):
        entries, total = _collect_entries(
            tree, query=None, file_type=None,
            sort_by="name", sort_order="asc",
            include_hidden=False, limit=0,
        )
        assert entries == []
        assert total > 0

    def test_limit_applied(self, tree):
        entries, total = _collect_entries(
            tree, query=None, file_type=None,
            sort_by="name", sort_order="asc",
            include_hidden=False, limit=1,
        )
        assert len(entries) == 1
        assert total > 1

    def test_nonexistent_directory(self, tmp_path):
        entries, total = _collect_entries(
            tmp_path / "nope", query=None, file_type=None,
            sort_by="name", sort_order="asc",
            include_hidden=False, limit=100,
        )
        assert entries == []
        assert total == 0

    def test_entry_structure(self, tree):
        entries, _ = _collect_entries(
            tree, query=None, file_type=None,
            sort_by="name", sort_order="asc",
            include_hidden=False, limit=100,
        )
        for entry in entries:
            assert "name" in entry
            assert "path" in entry
            assert "is_dir" in entry
            assert "kind" in entry
            assert "size_display" in entry

    def test_dirs_before_files(self, tree):
        entries, _ = _collect_entries(
            tree, query=None, file_type=None,
            sort_by="name", sort_order="asc",
            include_hidden=False, limit=100,
        )
        # Directories should come first
        found_file = False
        for entry in entries:
            if not entry["is_dir"]:
                found_file = True
            if found_file and entry["is_dir"]:
                pytest.fail("Directory found after a file")


# ---------------------------------------------------------------------------
# _build_file_results_context
# ---------------------------------------------------------------------------


class TestBuildFileResultsContext:
    """Test the full context builder."""

    def test_with_valid_path(self, tree, settings):
        request = MagicMock()
        with patch("file_organizer.web.files_routes.allowed_roots", return_value=[tree]), \
             patch("file_organizer.web.files_routes.resolve_selected_path", return_value=tree), \
             patch("file_organizer.web.files_routes.validate_depth"):
            ctx = _build_file_results_context(
                request, settings,
                path=str(tree), view="grid", query=None,
                file_type=None, sort_by="name", sort_order="asc", limit=50,
            )
        assert ctx["current_path"] == str(tree)
        assert ctx["view"] == "grid"
        assert "entries" in ctx
        assert ctx["error_message"] is None

    def test_with_no_path(self, tree, settings):
        request = MagicMock()
        with patch("file_organizer.web.files_routes.allowed_roots", return_value=[tree]), \
             patch("file_organizer.web.files_routes.resolve_selected_path", return_value=None):
            ctx = _build_file_results_context(
                request, settings,
                path=None, view="list", query=None,
                file_type=None, sort_by="name", sort_order="asc", limit=50,
            )
        assert ctx["error_message"] is not None

    def test_with_api_error(self, tree, settings):
        request = MagicMock()
        with patch("file_organizer.web.files_routes.allowed_roots", return_value=[tree]), \
             patch(
                 "file_organizer.web.files_routes.resolve_selected_path",
                 side_effect=ApiError(status_code=403, error="nope", message="bad"),
             ):
            ctx = _build_file_results_context(
                request, settings,
                path="/bad", view="grid", query=None,
                file_type=None, sort_by="name", sort_order="asc", limit=50,
            )
        assert "bad" in ctx["error_message"]

    def test_depth_validation_error(self, tree, settings):
        request = MagicMock()
        with patch("file_organizer.web.files_routes.allowed_roots", return_value=[tree]), \
             patch("file_organizer.web.files_routes.resolve_selected_path", return_value=tree), \
             patch(
                 "file_organizer.web.files_routes.validate_depth",
                 side_effect=ApiError(status_code=400, error="depth", message="too deep"),
             ):
            ctx = _build_file_results_context(
                request, settings,
                path=str(tree), view="grid", query=None,
                file_type=None, sort_by="name", sort_order="asc", limit=50,
            )
        assert "too deep" in ctx["error_message"]

    def test_invalid_view_normalized(self, tree, settings):
        request = MagicMock()
        with patch("file_organizer.web.files_routes.allowed_roots", return_value=[tree]), \
             patch("file_organizer.web.files_routes.resolve_selected_path", return_value=tree), \
             patch("file_organizer.web.files_routes.validate_depth"):
            ctx = _build_file_results_context(
                request, settings,
                path=str(tree), view="INVALID", query=None,
                file_type=None, sort_by="name", sort_order="asc", limit=50,
            )
        assert ctx["view"] == "grid"
