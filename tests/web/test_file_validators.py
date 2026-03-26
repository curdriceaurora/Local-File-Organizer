"""Tests for file_organizer.web.file_validators."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.api.exceptions import ApiError
from file_organizer.web.file_validators import (
    validate_file_not_exists,
    validate_file_size,
    validate_upload_filename,
    validate_upload_path,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def test_validate_upload_filename_rejects_empty() -> None:
    with pytest.raises(ApiError, match="must not be empty"):
        validate_upload_filename("")


def test_validate_upload_filename_rejects_hidden_by_basename() -> None:
    with pytest.raises(ApiError, match="Hidden files are not allowed"):
        validate_upload_filename("nested/.secret.txt")


def test_validate_upload_filename_allows_hidden_when_flagged() -> None:
    assert validate_upload_filename("nested/.secret.txt", allow_hidden=True) == "nested/.secret.txt"


def test_validate_upload_filename_returns_original_name() -> None:
    assert validate_upload_filename("nested/report.txt") == "nested/report.txt"


def test_validate_file_size_accepts_size_within_limit() -> None:
    assert validate_file_size(10, max_bytes=100) == 10


def test_validate_file_size_rejects_oversized_file() -> None:
    with pytest.raises(ApiError, match="exceeds upload limit"):
        validate_file_size(101, max_bytes=100)


def test_validate_file_not_exists_rejects_existing_target(tmp_path: Path) -> None:
    target = tmp_path / "report.txt"
    target.write_text("hello")

    with pytest.raises(ApiError, match="File already exists"):
        validate_file_not_exists(target, "report.txt")


def test_validate_file_not_exists_accepts_missing_target(tmp_path: Path) -> None:
    validate_file_not_exists(tmp_path / "missing.txt", "missing.txt")


def test_validate_upload_path_rejects_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ApiError, match="does not exist"):
        validate_upload_path(tmp_path / "missing")


def test_validate_upload_path_rejects_file(tmp_path: Path) -> None:
    target = tmp_path / "not-a-dir.txt"
    target.write_text("hello")

    with pytest.raises(ApiError, match="not a directory"):
        validate_upload_path(target)


def test_validate_upload_path_accepts_directory(tmp_path: Path) -> None:
    assert validate_upload_path(tmp_path) == tmp_path
