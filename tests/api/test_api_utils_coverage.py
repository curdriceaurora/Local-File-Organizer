"""Coverage tests for file_organizer.api.utils — uncovered lines/branches."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.api.exceptions import ApiError
from file_organizer.api.utils import file_info_from_path, is_hidden, resolve_path

pytestmark = pytest.mark.unit


class TestResolvePath:
    """Covers resolve_path error branches."""

    def test_no_allowed_paths(self) -> None:
        with pytest.raises(ApiError) as exc_info:
            resolve_path("/tmp/test", allowed_paths=None)
        assert exc_info.value.status_code == 403

    def test_empty_allowed_paths(self) -> None:
        with pytest.raises(ApiError) as exc_info:
            resolve_path("/tmp/test", allowed_paths=[])
        assert exc_info.value.status_code == 403

    def test_path_outside_roots(self, tmp_path: Path) -> None:
        with pytest.raises(ApiError) as exc_info:
            resolve_path("/etc/passwd", allowed_paths=[str(tmp_path)])
        assert exc_info.value.status_code == 403

    def test_path_inside_root(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        result = resolve_path(str(test_file), allowed_paths=[str(tmp_path)])
        assert result == Path(os.path.realpath(test_file))

    def test_value_error_in_commonpath(self) -> None:
        """On Windows, commonpath raises ValueError for paths on different drives."""
        with (
            patch("os.path.commonpath", side_effect=ValueError("different drives")),
            pytest.raises(ApiError) as exc_info,
        ):
            resolve_path("/tmp/test", allowed_paths=["/other/path"])
        assert exc_info.value.status_code == 403


class TestIsHidden:
    """Covers is_hidden."""

    def test_hidden_file(self) -> None:
        assert is_hidden(Path("/home/user/.config"))

    def test_non_hidden_file(self) -> None:
        assert not is_hidden(Path("/home/user/documents/file.txt"))

    def test_hidden_parent(self) -> None:
        assert is_hidden(Path("/home/user/.hidden/file.txt"))


class TestFileInfoFromPath:
    """Covers file_info_from_path edge cases."""

    def test_normal_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        info = file_info_from_path(f)
        assert info.name == "test.txt"
        assert info.size == 5

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ApiError) as exc_info:
            file_info_from_path(tmp_path / "nonexistent.txt")
        assert exc_info.value.status_code == 404

    def test_permission_error(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        with (
            patch.object(Path, "stat", side_effect=PermissionError("denied")),
            pytest.raises(ApiError) as exc_info,
        ):
            file_info_from_path(f)
        assert exc_info.value.status_code == 403

    def test_os_error(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello")
        with (
            patch.object(Path, "stat", side_effect=OSError("io error")),
            pytest.raises(ApiError) as exc_info,
        ):
            file_info_from_path(f)
        assert exc_info.value.status_code == 500

    def test_file_without_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "Makefile"
        f.write_text("all:")
        info = file_info_from_path(f)
        assert info.file_type == ""

    def test_creation_time_with_birthtime(self, tmp_path: Path) -> None:
        """Validates the normal path where st_birthtime is available (macOS)."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        info = file_info_from_path(f)
        assert info.created is not None
        assert info.modified is not None
