"""Tests for file_organizer.api.utils module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.api.exceptions import ApiError
from file_organizer.api.utils import file_info_from_path, is_hidden, resolve_path


# ---------------------------------------------------------------------------
# resolve_path
# ---------------------------------------------------------------------------
class TestResolvePath:
    """Tests for the resolve_path helper."""

    def test_valid_path_within_allowed_root(self, tmp_path: Path) -> None:
        target = tmp_path / "subdir"
        target.mkdir()
        result = resolve_path(str(target), allowed_paths=[str(tmp_path)])
        assert result == target.resolve()

    def test_path_outside_allowed_roots_raises_403(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        allowed_root = tmp_path / "allowed"
        allowed_root.mkdir()
        with pytest.raises(ApiError) as exc_info:
            resolve_path(str(outside), allowed_paths=[str(allowed_root)])
        assert exc_info.value.status_code == 403
        assert exc_info.value.error == "path_not_allowed"

    def test_none_allowed_paths_raises_403(self, tmp_path: Path) -> None:
        with pytest.raises(ApiError) as exc_info:
            resolve_path(str(tmp_path), allowed_paths=None)
        assert exc_info.value.status_code == 403

    def test_empty_list_allowed_paths_raises_403(self, tmp_path: Path) -> None:
        with pytest.raises(ApiError) as exc_info:
            resolve_path(str(tmp_path), allowed_paths=[])
        assert exc_info.value.status_code == 403

    def test_tilde_expansion(self, tmp_path: Path) -> None:
        home = Path.home()
        # Use home dir itself as allowed root so the resolved path is allowed.
        result = resolve_path("~", allowed_paths=[str(home)])
        assert result == home.resolve()

    def test_symlink_resolution(self, tmp_path: Path) -> None:
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real_dir)
        result = resolve_path(str(link), allowed_paths=[str(tmp_path)])
        assert result == real_dir.resolve()

    def test_file_inside_allowed_root(self, tmp_path: Path) -> None:
        f = tmp_path / "data.txt"
        f.write_text("hello")
        result = resolve_path(str(f), allowed_paths=[str(tmp_path)])
        assert result == f.resolve()

    def test_path_prefix_attack_blocked(self, tmp_path: Path) -> None:
        # Regression for #672: str.startswith() would allow "/allowed_dir_suffix"
        # to pass when "/allowed_dir" is the allowed root.
        # Path.is_relative_to() correctly rejects this because the directory
        # boundary is respected (it's not a child path).
        allowed = tmp_path / "data"
        allowed.mkdir()
        attack = tmp_path / "data_extra"
        attack.mkdir()
        with pytest.raises(ApiError) as exc_info:
            resolve_path(str(attack), allowed_paths=[str(allowed)])
        assert exc_info.value.status_code == 403
        assert exc_info.value.error == "path_not_allowed"

    def test_dotdot_traversal_via_subdirectory_blocked(self, tmp_path: Path) -> None:
        # Ensure that a path with embedded ".." that would escape the root is blocked.
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        # Construct a path that goes through the allowed root and back out
        traversal = str(allowed) + "/../outside"
        with pytest.raises(ApiError) as exc_info:
            resolve_path(traversal, allowed_paths=[str(allowed)])
        assert exc_info.value.status_code == 403

    def test_symlink_escaping_allowed_root_blocked(self, tmp_path: Path) -> None:
        # A symlink inside the allowed root that points outside must be blocked.
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "secret"
        outside.mkdir()
        # Create a symlink inside allowed that points to outside
        link = allowed / "escape_link"
        link.symlink_to(outside)
        with pytest.raises(ApiError) as exc_info:
            resolve_path(str(link), allowed_paths=[str(allowed)])
        assert exc_info.value.status_code == 403

    def test_windows_drive_qualified_path_blocked(self, tmp_path: Path) -> None:
        # Drive-qualified input must never be accepted when it is outside the
        # configured allowlist root (Windows and non-Windows behavior alike).
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        with pytest.raises(ApiError) as exc_info:
            resolve_path(r"C:\Windows\System32", allowed_paths=[str(allowed)])
        assert exc_info.value.status_code == 403
        assert exc_info.value.error == "path_not_allowed"

    def test_unc_path_blocked_when_outside_allowlist(self, tmp_path: Path) -> None:
        # UNC-style paths are treated as out-of-scope unless explicitly under an
        # allowed root; this guards Windows network-share escape cases.
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        with pytest.raises(ApiError) as exc_info:
            resolve_path(r"\\server\share\secret.txt", allowed_paths=[str(allowed)])
        assert exc_info.value.status_code == 403
        assert exc_info.value.error == "path_not_allowed"

    def test_returns_path_object(self, tmp_path: Path) -> None:
        result = resolve_path(str(tmp_path), allowed_paths=[str(tmp_path)])
        assert isinstance(result, Path)
        assert result.is_absolute()


# ---------------------------------------------------------------------------
# is_hidden
# ---------------------------------------------------------------------------
class TestIsHidden:
    """Tests for the is_hidden helper."""

    def test_dotfile_is_hidden(self) -> None:
        assert is_hidden(Path(".bashrc")) is True

    def test_dotdir_is_hidden(self) -> None:
        assert is_hidden(Path(".config/settings.json")) is True

    def test_normal_path_not_hidden(self) -> None:
        assert is_hidden(Path("documents/report.pdf")) is False

    def test_root_path_not_hidden(self) -> None:
        assert is_hidden(Path("toplevel")) is False

    def test_relative_dotfile(self) -> None:
        assert is_hidden(Path(".env")) is True

    def test_nested_normal_path(self) -> None:
        assert is_hidden(Path("src/file_organizer/api/utils.py")) is False


# ---------------------------------------------------------------------------
# file_info_from_path
# ---------------------------------------------------------------------------
class TestFileInfoFromPath:
    """Tests for the file_info_from_path helper."""

    def test_valid_file_returns_file_info(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.txt"
        f.write_text("content")
        info = file_info_from_path(f)
        assert info.path == str(f)
        assert info.name == "sample.txt"
        assert info.size == len("content")
        assert info.file_type == ".txt"
        assert info.created is not None
        assert info.modified is not None

    def test_mime_type_txt(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.txt"
        f.write_text("hi")
        info = file_info_from_path(f)
        assert info.mime_type is not None
        assert "text" in info.mime_type

    def test_mime_type_py(self, tmp_path: Path) -> None:
        f = tmp_path / "script.py"
        f.write_text("print(1)")
        info = file_info_from_path(f)
        # Python files may be text/x-python or similar
        assert info.mime_type is None or "python" in info.mime_type or "text" in info.mime_type

    def test_missing_file_raises_404(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.txt"
        with pytest.raises(ApiError) as exc_info:
            file_info_from_path(missing)
        assert exc_info.value.status_code == 404
        assert exc_info.value.error == "file_not_found"

    def test_permission_denied_raises_403(self, tmp_path: Path) -> None:
        f = tmp_path / "secret.txt"
        f.write_text("x")
        with patch.object(Path, "stat", side_effect=PermissionError("denied")):
            with pytest.raises(ApiError) as exc_info:
                file_info_from_path(f)
            assert exc_info.value.status_code == 403
            assert exc_info.value.error == "file_access_error"

    def test_os_error_raises_500(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.txt"
        f.write_text("x")
        with patch.object(Path, "stat", side_effect=OSError("disk error")):
            with pytest.raises(ApiError) as exc_info:
                file_info_from_path(f)
            assert exc_info.value.status_code == 500
            assert exc_info.value.error == "file_access_error"

    def test_no_extension_file_type(self, tmp_path: Path) -> None:
        f = tmp_path / "Makefile"
        f.write_text("all:")
        info = file_info_from_path(f)
        assert info.file_type == ""

    def test_size_matches(self, tmp_path: Path) -> None:
        content = "hello world" * 100
        f = tmp_path / "big.txt"
        f.write_text(content)
        info = file_info_from_path(f)
        assert info.size == os.path.getsize(f)
