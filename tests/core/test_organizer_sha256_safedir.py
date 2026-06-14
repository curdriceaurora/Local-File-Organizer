"""Regression tests for ``FileOrganizer._sha256_via_safedir`` (PR3h).

The dedup hasher routes file reads through ``SafeDir.open_root`` +
``open_for_reader`` so a symlink swapped between organize-time
enumeration and the hash read is refused. This file covers every
branch the SafeDir migration introduced:

- happy path on a real on-disk file (no mocks) — verifies the SHA-256
  matches a stdlib reference
- ``SymlinkRejected`` returns ``None`` (caller treats as "unknown
  hash" and keeps the file rather than dropping it)
- ``NotImplementedError`` falls back to the legacy ``path.open(...)``
- ``os.fdopen`` failure after ``open_for_reader`` returned a raw fd:
  the fd MUST be explicitly closed
- generic ``OSError`` from SafeDir returns ``None``
- legacy fallback ``OSError`` returns ``None``
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.core.organizer import FileOrganizer
from file_organizer.utils.safedir import SymlinkRejected

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
    pytest.mark.integration,
]


class TestSha256ViaSafedirHappyPath:
    def test_real_file_hash_matches_stdlib(self, tmp_path: Path) -> None:
        target = tmp_path / "x.bin"
        payload = b"the quick brown fox jumps over the lazy dog"
        target.write_bytes(payload)
        expected = hashlib.sha256(payload).hexdigest()
        assert FileOrganizer._sha256_via_safedir(target) == expected

    def test_large_file_chunked_hash(self, tmp_path: Path) -> None:
        """Hash boundary: input larger than the 64 KiB chunk size must
        still match the stdlib digest."""
        target = tmp_path / "big.bin"
        payload = b"a" * (128 * 1024 + 17)  # spans two chunks + tail
        target.write_bytes(payload)
        assert FileOrganizer._sha256_via_safedir(target) == hashlib.sha256(payload).hexdigest()


@pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")
class TestSha256ViaSafedirBranches:
    def test_symlink_rejected_returns_none(self, tmp_path: Path) -> None:
        target = tmp_path / "real.bin"
        target.write_bytes(b"never read")
        with patch(
            "file_organizer.core.organizer.SafeDir.open_root",
            side_effect=SymlinkRejected("real.bin"),
        ):
            assert FileOrganizer._sha256_via_safedir(target) is None

    def test_not_implemented_falls_back_to_legacy_open(self, tmp_path: Path) -> None:
        target = tmp_path / "fallback.bin"
        payload = b"fallback bytes"
        target.write_bytes(payload)
        with patch(
            "file_organizer.core.organizer.SafeDir.open_root",
            side_effect=NotImplementedError("no dir_fd"),
        ):
            assert FileOrganizer._sha256_via_safedir(target) == hashlib.sha256(payload).hexdigest()

    def test_fdopen_failure_closes_bare_fd(self, tmp_path: Path) -> None:
        target = tmp_path / "real.bin"
        target.write_bytes(b"never read")
        sentinel_fd = 4242

        fake_safe_dir = MagicMock()
        fake_safe_dir.open_for_reader.return_value = sentinel_fd
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_safe_dir
        fake_cm.__exit__.return_value = False

        with (
            patch("file_organizer.core.organizer.SafeDir.open_root", return_value=fake_cm),
            patch("file_organizer.core.organizer.os.fdopen", side_effect=OSError("fdopen failed")),
            patch("file_organizer.core.organizer.os.close") as mock_close,
        ):
            assert FileOrganizer._sha256_via_safedir(target) is None
            mock_close.assert_called_once_with(sentinel_fd)

    def test_safedir_oserror_returns_none(self, tmp_path: Path) -> None:
        target = tmp_path / "x.bin"
        with patch(
            "file_organizer.core.organizer.SafeDir.open_root",
            side_effect=OSError("no such file"),
        ):
            assert FileOrganizer._sha256_via_safedir(target) is None

    def test_safedir_valueerror_returns_none(self, tmp_path: Path) -> None:
        """SafeDir's name validation rejects filenames containing
        backslash / NUL / path separators with ``ValueError``. On
        POSIX such filenames are legal in the filesystem, so a
        ``safe_walk`` enumerator can yield them. The helper must treat
        them like any other unreadable file and return ``None`` rather
        than letting the ``ValueError`` abort the entire organize run.
        """
        target = tmp_path / "ok.bin"
        target.write_bytes(b"data")
        with patch(
            "file_organizer.core.organizer.SafeDir.open_root",
            side_effect=ValueError("name 'a\\b' contains path separator"),
        ):
            assert FileOrganizer._sha256_via_safedir(target) is None


@pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")
class TestSha256ViaSafedirLegacyFallback:
    def test_legacy_open_oserror_returns_none(self, tmp_path: Path) -> None:
        """When SafeDir is unavailable AND the legacy path-open also
        fails (e.g. file doesn't exist), the function returns None."""
        target = tmp_path / "ghost.bin"
        # File never created.
        with patch(
            "file_organizer.core.organizer.SafeDir.open_root",
            side_effect=NotImplementedError(),
        ):
            assert FileOrganizer._sha256_via_safedir(target) is None


@pytest.mark.skipif(sys.platform == "win32", reason="SafeDir is POSIX-only")
class TestSha256ViaSafedirAnchored:
    """``scan_root`` enables anchored traversal (#286): every intermediate
    component between scan_root and the file is O_NOFOLLOW-checked."""

    def test_nested_file_under_real_dirs_hashes(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        nested = root / "a" / "b"
        nested.mkdir(parents=True)
        target = nested / "doc.bin"
        payload = b"nested payload"
        target.write_bytes(payload)
        assert (
            FileOrganizer._sha256_via_safedir(target, scan_root=root)
            == hashlib.sha256(payload).hexdigest()
        )

    def test_symlinked_ancestor_is_refused(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        (root / "a").mkdir(parents=True)
        outside = tmp_path / "outside"
        (outside / "a").mkdir(parents=True)
        secret = outside / "a" / "doc.bin"
        secret.write_bytes(b"TOP SECRET")
        # Swap root/a -> outside/a after "enumeration".
        (root / "a").rmdir()
        try:
            (root / "a").symlink_to(outside / "a")
        except OSError:
            pytest.skip("symlink creation not supported on this filesystem")
        # The path the walk would have yielded under the trusted root.
        target = root / "a" / "doc.bin"
        assert FileOrganizer._sha256_via_safedir(target, scan_root=root) is None

    def test_path_outside_scan_root_returns_none(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside.bin"
        outside.write_bytes(b"data")
        assert FileOrganizer._sha256_via_safedir(outside, scan_root=root) is None

    def test_dotdot_escape_returns_none(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (tmp_path / "secret.bin").write_bytes(b"data")
        escape = root / ".." / "secret.bin"
        assert FileOrganizer._sha256_via_safedir(escape, scan_root=root) is None
