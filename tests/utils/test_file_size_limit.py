"""Tests for file size limits in file_readers (Issue #339 - DoS prevention).

These tests verify that the file size gate correctly rejects files that exceed
MAX_FILE_SIZE_BYTES before any file I/O or memory allocation occurs, preventing
denial-of-service attacks via arbitrarily large files.

Covered APIs:
- FileTooLargeError exception class
- MAX_FILE_SIZE_BYTES constant
- _check_file_size(path, max_bytes) helper
- Size gates at the top of read_file(), read_docx_file(),
  read_presentation_file(), read_ebook_file(), read_tar_file()
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Issue #339 implementation is required — import unconditionally so that a
# missing symbol causes a collection error rather than silent test skipping.
from file_organizer.utils.file_readers import (
    MAX_FILE_SIZE_BYTES,
    FileTooLargeError,
    _check_file_size,
    read_docx_file,  # noqa: F401 — verified via importlib in TestUnboundedReadersSizeGate
    read_ebook_file,  # noqa: F401 — verified via importlib in TestUnboundedReadersSizeGate
    read_file,
    read_presentation_file,  # noqa: F401 — verified via importlib in TestUnboundedReadersSizeGate
    read_tar_file,  # noqa: F401 — verified via importlib in TestUnboundedReadersSizeGate
)

# Marker kept for any tests that remain genuinely optional (none currently).
_needs_stream_a = pytest.mark.usefixtures()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ONE_MB = 1 * 1024 * 1024  # 1 MiB


def _make_stat(size: int) -> os.stat_result:
    """Return a minimal os.stat_result with st_size set to *size*."""
    fake = MagicMock(spec=os.stat_result)
    fake.st_size = size
    return fake


# ---------------------------------------------------------------------------
# TestCheckFileSizeHelper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckFileSizeHelper:
    """Unit tests for the _check_file_size() helper introduced by Stream A."""

    @_needs_stream_a
    def test_small_file_passes(self) -> None:
        """A 1 MB file is well below the limit; no exception should be raised."""
        with patch("pathlib.Path.stat", return_value=_make_stat(ONE_MB)):
            _check_file_size(Path("any_file.txt"))  # must not raise

    @_needs_stream_a
    def test_file_at_limit_passes(self) -> None:
        """A file whose size equals exactly MAX_FILE_SIZE_BYTES is allowed."""
        with patch("pathlib.Path.stat", return_value=_make_stat(MAX_FILE_SIZE_BYTES)):
            _check_file_size(Path("boundary_file.txt"))  # must not raise

    @_needs_stream_a
    def test_file_over_limit_raises(self) -> None:
        """A file one byte over the limit must raise FileTooLargeError."""
        oversized = MAX_FILE_SIZE_BYTES + 1
        with patch("pathlib.Path.stat", return_value=_make_stat(oversized)):
            with pytest.raises(FileTooLargeError):
                _check_file_size(Path("oversized.txt"))

    @_needs_stream_a
    def test_custom_limit(self) -> None:
        """Callers can pass a custom max_bytes; the helper must honour it."""
        custom_limit = 1024  # 1 KiB
        file_size = 2048  # 2 KiB — exceeds the custom limit
        with patch("pathlib.Path.stat", return_value=_make_stat(file_size)):
            with pytest.raises(FileTooLargeError):
                _check_file_size(Path("custom_limit.dat"), max_bytes=custom_limit)

    @_needs_stream_a
    def test_stat_oserror_is_ignored(self) -> None:
        """If os.stat() raises OSError the helper must silently return.

        The underlying reader is responsible for handling missing/unreadable
        files; the size gate should not shadow those errors.
        """
        with patch("pathlib.Path.stat", side_effect=OSError("permission denied")):
            _check_file_size(Path("inaccessible.txt"))  # must not raise

    @_needs_stream_a
    def test_error_message_contains_size_info(self) -> None:
        """FileTooLargeError message must mention the file size in MB so that
        users and log aggregators can diagnose the rejection at a glance."""
        oversized = MAX_FILE_SIZE_BYTES + 1
        with patch("pathlib.Path.stat", return_value=_make_stat(oversized)):
            with pytest.raises(FileTooLargeError, match=r"(?i)mb|megabyte|bytes"):
                _check_file_size(Path("too_big.bin"))


# ---------------------------------------------------------------------------
# TestReadFileDispatcherSizeGate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReadFileDispatcherSizeGate:
    """Tests that read_file() rejects oversized paths before dispatching."""

    @_needs_stream_a
    def test_read_file_rejects_oversized(self, tmp_path: Path) -> None:
        """read_file() must raise FileTooLargeError without reading any content
        when the file exceeds MAX_FILE_SIZE_BYTES."""
        fake_txt = tmp_path / "huge.txt"
        # The file does not need real content; stat is mocked.
        fake_txt.write_text("x")

        huge_stat = _make_stat(MAX_FILE_SIZE_BYTES + 1)
        with patch.object(Path, "stat", return_value=huge_stat):
            with pytest.raises(FileTooLargeError):
                read_file(str(fake_txt))

    @_needs_stream_a
    def test_read_file_passes_normal_size(self, tmp_path: Path) -> None:
        """read_file() must call through to the underlying reader when the file
        is within the size limit."""
        fake_txt = tmp_path / "normal.txt"
        fake_txt.write_text("Hello, world!")

        small_stat = _make_stat(ONE_MB)  # well within limit
        # Patch at the Path level so _check_file_size sees the mock stat, then
        # let the real text reader run (the file exists and is readable).
        with patch.object(Path, "stat", return_value=small_stat):
            result = read_file(str(fake_txt))

        # The real reader should return the file's content (or at minimum not
        # raise FileTooLargeError).
        assert result is not None


# ---------------------------------------------------------------------------
# TestUnboundedReadersSizeGate
# ---------------------------------------------------------------------------

_READER_PARAMS = [
    ("read_docx_file", "docx"),
    ("read_presentation_file", "pptx"),
    ("read_ebook_file", "epub"),
    ("read_tar_file", "tar"),
]


@pytest.mark.unit
class TestUnboundedReadersSizeGate:
    """Each previously-unbounded reader must gate on file size before I/O."""

    @_needs_stream_a
    @pytest.mark.parametrize("reader_name,ext", _READER_PARAMS)
    def test_reader_rejects_oversized(
        self,
        reader_name: str,
        ext: str,
        tmp_path: Path,
    ) -> None:
        """Each named reader must raise FileTooLargeError for an oversized path
        without performing any actual file parsing.

        The file does not need to be valid for its format — the size check must
        occur *before* opening or parsing the file.
        """
        import importlib

        module = importlib.import_module("file_organizer.utils.file_readers")
        reader = getattr(module, reader_name)

        # Create a dummy file so Path resolution does not fail on missing path.
        dummy = tmp_path / f"huge.{ext}"
        dummy.write_bytes(b"\x00" * 16)  # tiny content; stat is mocked

        huge_stat = _make_stat(MAX_FILE_SIZE_BYTES + 1)

        with patch.object(Path, "stat", return_value=huge_stat):
            with pytest.raises(FileTooLargeError):
                reader(dummy)
