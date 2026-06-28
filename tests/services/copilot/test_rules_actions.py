"""Tests for copilot rule filesystem actions."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.services.copilot.rules.actions import (
    ConflictStrategy,
    apply_hardlink,
    apply_symlink,
    copy_file,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.integration]


def test_hardlink_creates_second_view(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")

    result = apply_hardlink(source, tmp_path / "links" / "source.txt", ConflictStrategy.RENAME_NEW)

    assert result.skipped is False
    assert result.destination.read_text(encoding="utf-8") == "hello"
    assert os.stat(source).st_ino == os.stat(result.destination).st_ino


def test_symlink_creates_pointer_to_source(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")

    result = apply_symlink(source, tmp_path / "links" / "source.txt", ConflictStrategy.RENAME_NEW)

    assert result.skipped is False
    assert result.destination.is_symlink()
    assert result.destination.resolve() == source


def test_conflict_skip_leaves_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "dest.txt"
    source.write_text("new", encoding="utf-8")
    destination.write_text("old", encoding="utf-8")

    result = copy_file(source, destination, ConflictStrategy.SKIP)

    assert result.skipped is True
    assert destination.read_text(encoding="utf-8") == "old"


def test_conflict_rename_new_preserves_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "dest.txt"
    source.write_text("new", encoding="utf-8")
    destination.write_text("old", encoding="utf-8")

    result = copy_file(source, destination, ConflictStrategy.RENAME_NEW)

    assert result.skipped is False
    assert destination.read_text(encoding="utf-8") == "old"
    assert result.destination == tmp_path / "dest_1.txt"
    assert result.destination.read_text(encoding="utf-8") == "new"
def test_copy_file_clean_success(tmp_path: Path) -> None:
    """Tests copying a file where no destination or parent directory exists yet."""
    source = tmp_path / "source.txt"
    destination = tmp_path / "nested_dir" / "dest.txt"
    source.write_text("clean copy", encoding="utf-8")

    result = copy_file(source, destination, ConflictStrategy.SKIP)

    assert result.skipped is False
    assert result.destination == destination
    assert destination.read_text(encoding="utf-8") == "clean copy"


def test_conflict_overwrite_file(tmp_path: Path) -> None:
    """Tests that ConflictStrategy.OVERWRITE successfully replaces an existing file."""
    source = tmp_path / "source.txt"
    destination = tmp_path / "dest.txt"
    source.write_text("incoming data", encoding="utf-8")
    destination.write_text("stale data", encoding="utf-8")

    result = copy_file(source, destination, ConflictStrategy.OVERWRITE)

    assert result.skipped is False
    assert result.destination == destination
    assert destination.read_text(encoding="utf-8") == "incoming data"


def test_conflict_overwrite_directory_raises_error(tmp_path: Path) -> None:
    """Tests that trying to overwrite a real directory raises an IsADirectoryError."""
    source = tmp_path / "source.txt"
    destination = tmp_path / "target_dir"
    source.write_text("data", encoding="utf-8")
    destination.mkdir()

    with pytest.raises(IsADirectoryError, match="Cannot overwrite directory"):
        copy_file(source, destination, ConflictStrategy.OVERWRITE)


def test_conflict_rename_multiple_increments(tmp_path: Path) -> None:
    """Tests the while-loop branch where dest.txt and dest_1.txt both exist."""
    source = tmp_path / "source.txt"
    source.write_text("brand new", encoding="utf-8")
    (tmp_path / "dest.txt").write_text("original", encoding="utf-8")
    (tmp_path / "dest_1.txt").write_text("first conflict", encoding="utf-8")

    result = copy_file(source, tmp_path / "dest.txt", ConflictStrategy.RENAME_NEW)

    assert result.destination == tmp_path / "dest_2.txt"
    assert result.destination.read_text(encoding="utf-8") == "brand new"


def test_copy_file_exception_unlinks_partial_file(tmp_path: Path) -> None:
    """Tests the try/except block in copy_file unlinks the target if copying fails."""
    source = tmp_path / "source.txt"
    destination = tmp_path / "dest.txt"
    source.write_text("payload", encoding="utf-8")

    # Force an exception during the stream copy to hit the cleanup block
    with patch("shutil.copyfileobj", side_effect=RuntimeError("Disk failure simulation")):
        with pytest.raises(RuntimeError, match="Disk failure simulation"):
            copy_file(source, destination, ConflictStrategy.SKIP)

    # Ensure the destination wasn't left behind in a corrupted or partial state
    assert not destination.exists()


def test_link_strategies_handling_skipped_conflicts(tmp_path: Path) -> None:
    """Ensures hardlink and symlink helpers accurately catch and return skipped actions."""
    source = tmp_path / "source.txt"
    destination = tmp_path / "dest.txt"
    source.write_text("source", encoding="utf-8")
    destination.write_text("existing", encoding="utf-8")

    hl_result = apply_hardlink(source, destination, ConflictStrategy.SKIP)
    assert hl_result.skipped is True
    assert hl_result.reason == "exists"

    sl_result = apply_symlink(source, destination, ConflictStrategy.SKIP)
    assert sl_result.skipped is True
    assert sl_result.reason == "exists"
