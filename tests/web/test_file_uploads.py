"""Tests for web upload persistence helpers."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from file_organizer.api.exceptions import ApiError
from file_organizer.web.file_uploads import process_file_uploads, save_upload

pytestmark = [pytest.mark.ci, pytest.mark.unit]


def _upload(name: str, data: bytes) -> SimpleNamespace:
    return SimpleNamespace(filename=name, file=io.BytesIO(data))


def test_save_upload_rejects_name_that_cannot_be_sanitized(tmp_path: Path) -> None:
    with patch("file_organizer.web.file_uploads.sanitize_upload_name", return_value=None):
        error = save_upload(_upload("bad.txt", b"hello"), tmp_path, allow_hidden=False)

    assert error == "Rejected bad.txt: invalid filename."


def test_process_file_uploads_closes_files_and_reports_errors(tmp_path: Path) -> None:
    upload = _upload("big.bin", b"hello")

    with patch(
        "file_organizer.web.file_uploads.validate_file_size",
        side_effect=ApiError(status_code=400, error="file_too_large", message="too large"),
    ):
        saved, errors = process_file_uploads([upload], tmp_path)

    assert saved == 0
    assert errors == ["big.bin exceeds upload size limit."]
    assert upload.file.closed
    assert not (tmp_path / "big.bin").exists()


def test_process_file_uploads_saves_hidden_file_when_allowed(tmp_path: Path) -> None:
    saved, errors = process_file_uploads(
        [_upload(".env", b"KEY=value")], tmp_path, allow_hidden=True
    )

    assert saved == 1
    assert errors == []
    assert (tmp_path / ".env").read_bytes() == b"KEY=value"


def test_process_file_uploads_rejects_hidden_file_by_default(tmp_path: Path) -> None:
    saved, errors = process_file_uploads([_upload(".env", b"KEY=value")], tmp_path)

    assert saved == 0
    assert errors
    assert not (tmp_path / ".env").exists()
