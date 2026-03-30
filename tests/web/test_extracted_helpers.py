"""Tests for helpers extracted during complexity reduction (#1022).

Covers the newly extracted functions in file_operations.py and
profile_merger.py to satisfy the diff-coverage gate.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.web.file_operations import (
    _creation_sort_key,
    _dir_entry,
    _file_entry,
    _filter_children,
    _save_upload,
    _sort_files,
)

pytestmark = [pytest.mark.ci]


# ---------------------------------------------------------------------------
# _creation_sort_key
# ---------------------------------------------------------------------------


class TestCreationSortKey:
    """Tests for the _creation_sort_key helper."""

    def test_none_stat_returns_zero(self) -> None:
        assert _creation_sort_key(None) == 0.0

    def test_stat_with_birthtime(self) -> None:
        stat = SimpleNamespace(st_birthtime=1234.5, st_ctime=999.0, st_mtime=888.0)
        assert _creation_sort_key(stat) == 1234.5

    def test_stat_without_birthtime_non_nt(self) -> None:
        stat = SimpleNamespace(st_ctime=999.0, st_mtime=888.0)
        with patch.object(os, "name", "posix"):
            assert _creation_sort_key(stat) == 888.0

    def test_stat_without_birthtime_on_nt(self) -> None:
        stat = SimpleNamespace(st_ctime=999.0, st_mtime=888.0)
        with patch.object(os, "name", "nt"):
            assert _creation_sort_key(stat) == 999.0


# ---------------------------------------------------------------------------
# _filter_children
# ---------------------------------------------------------------------------


class TestFilterChildren:
    """Tests for the _filter_children helper."""

    def test_splits_dirs_and_files(self, tmp_path: Path) -> None:
        d = tmp_path / "subdir"
        d.mkdir()
        f = tmp_path / "file.txt"
        f.write_text("x")
        dirs, files = _filter_children(
            [d, f], query_token=None, include_hidden=True, allowed_types=None
        )
        assert dirs == [d]
        assert files == [f]

    def test_excludes_hidden_when_requested(self, tmp_path: Path) -> None:
        hidden = tmp_path / ".hidden"
        hidden.write_text("x")
        visible = tmp_path / "visible.txt"
        visible.write_text("x")
        _, files = _filter_children(
            [hidden, visible], query_token=None, include_hidden=False, allowed_types=None
        )
        assert files == [visible]

    def test_query_filter(self, tmp_path: Path) -> None:
        a = tmp_path / "apple.txt"
        a.write_text("x")
        b = tmp_path / "banana.txt"
        b.write_text("x")
        _, files = _filter_children(
            [a, b], query_token="apple", include_hidden=True, allowed_types=None
        )
        assert files == [a]

    def test_type_filter(self, tmp_path: Path) -> None:
        txt = tmp_path / "doc.txt"
        txt.write_text("x")
        png = tmp_path / "img.png"
        png.write_text("x")
        _, files = _filter_children(
            [txt, png], query_token=None, include_hidden=True, allowed_types={".txt"}
        )
        assert files == [txt]


# ---------------------------------------------------------------------------
# _sort_files
# ---------------------------------------------------------------------------


class TestSortFiles:
    """Tests for the _sort_files helper."""

    def test_sort_by_name_asc(self, tmp_path: Path) -> None:
        b = tmp_path / "beta.txt"
        b.write_text("x")
        a = tmp_path / "alpha.txt"
        a.write_text("x")
        files = [b, a]
        _sort_files(files, "name", "asc", {})
        assert files == [a, b]

    def test_sort_by_name_desc(self, tmp_path: Path) -> None:
        a = tmp_path / "alpha.txt"
        a.write_text("x")
        b = tmp_path / "beta.txt"
        b.write_text("x")
        files = [a, b]
        _sort_files(files, "name", "desc", {})
        assert files == [b, a]


# ---------------------------------------------------------------------------
# _dir_entry / _file_entry
# ---------------------------------------------------------------------------


class TestDirEntry:
    """Tests for the _dir_entry helper."""

    def test_returns_folder_dict(self, tmp_path: Path) -> None:
        d = tmp_path / "subdir"
        d.mkdir()
        entry = _dir_entry(d)
        assert entry["name"] == "subdir"
        assert entry["is_dir"] is True
        assert entry["kind"] == "folder"

    def test_oserror_fallback(self) -> None:
        missing = Path("/nonexistent/dir")
        entry = _dir_entry(missing)
        assert entry["name"] == "dir"
        assert entry["is_dir"] is True


class TestFileEntry:
    """Tests for the _file_entry helper."""

    def test_returns_file_dict(self, tmp_path: Path) -> None:
        f = tmp_path / "note.txt"
        f.write_text("hello")
        entry = _file_entry(f)
        assert entry["name"] == "note.txt"
        assert entry["is_dir"] is False


# ---------------------------------------------------------------------------
# _save_upload
# ---------------------------------------------------------------------------


class TestSaveUpload:
    """Tests for the _save_upload helper."""

    def test_no_filename_returns_empty_string(self, tmp_path: Path) -> None:
        upload = MagicMock()
        upload.filename = ""
        result = _save_upload(upload, tmp_path, allow_hidden=False)
        assert result == ""

    def test_oserror_during_write(self, tmp_path: Path) -> None:
        upload = MagicMock()
        upload.filename = "test.txt"
        upload.file.read.side_effect = OSError("disk full")
        result = _save_upload(upload, tmp_path, allow_hidden=False)
        assert result is not None
        assert "Failed to save" in result


# ---------------------------------------------------------------------------
# _find_section_conflicts (profile_merger)
# ---------------------------------------------------------------------------


class TestFindSectionConflicts:
    """Tests for ProfileMerger._find_section_conflicts."""

    def test_finds_conflicting_values(self) -> None:
        from file_organizer.services.intelligence.profile_merger import ProfileMerger

        p1 = SimpleNamespace(preferences={"global": {"theme": "dark"}})
        p2 = SimpleNamespace(preferences={"global": {"theme": "light"}})
        conflicts = ProfileMerger._find_section_conflicts([p1, p2], "global", "global")
        assert "global.theme" in conflicts
        assert conflicts["global.theme"] == ["dark", "light"]

    def test_no_conflicts_for_identical_values(self) -> None:
        from file_organizer.services.intelligence.profile_merger import ProfileMerger

        p1 = SimpleNamespace(preferences={"global": {"theme": "dark"}})
        p2 = SimpleNamespace(preferences={"global": {"theme": "dark"}})
        conflicts = ProfileMerger._find_section_conflicts([p1, p2], "global", "global")
        assert conflicts == {}

    def test_none_preferences_handled(self) -> None:
        from file_organizer.services.intelligence.profile_merger import ProfileMerger

        p1 = SimpleNamespace(preferences=None)
        p2 = SimpleNamespace(preferences={"global": {"k": "v"}})
        conflicts = ProfileMerger._find_section_conflicts([p1, p2], "global", "global")
        assert conflicts == {}

    def test_missing_section_handled(self) -> None:
        from file_organizer.services.intelligence.profile_merger import ProfileMerger

        p1 = SimpleNamespace(preferences={"global": {"k": "v1"}})
        p2 = SimpleNamespace(preferences={})
        conflicts = ProfileMerger._find_section_conflicts([p1, p2], "global", "global")
        assert conflicts == {}
