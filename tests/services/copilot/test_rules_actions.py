"""Tests for copilot rule filesystem actions."""

from __future__ import annotations

import os
from pathlib import Path

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
