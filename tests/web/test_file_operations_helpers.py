"""Tests for extracted helper flows in file_organizer.web.file_operations."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.exceptions import ApiError
from file_organizer.web.file_operations import (
    build_preview_context,
    build_tree_context,
    generate_thumbnail,
    process_file_uploads,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit]


@pytest.fixture
def settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(allowed_paths=[str(tmp_path)])


class TestBuildTreeContext:
    def test_returns_roots_when_no_path(self, tmp_path: Path, settings: ApiSettings) -> None:
        with patch("file_organizer.web.file_operations.allowed_roots", return_value=[tmp_path]):
            context = build_tree_context(None, settings, depth=0, active=None)

        assert context["error_message"] is None
        assert context["nodes"][0]["is_root"] is True

    def test_returns_error_when_resolve_fails(self, settings: ApiSettings) -> None:
        with patch(
            "file_organizer.web.file_operations.resolve_path",
            side_effect=ApiError(status_code=400, error="bad", message="bad path"),
        ):
            context = build_tree_context("/bad", settings, depth=1, active=None)

        assert context["error_message"] == "bad path"

    def test_returns_nodes_for_expanded_path(self, tmp_path: Path, settings: ApiSettings) -> None:
        node = {"name": "child"}
        with (
            patch("file_organizer.web.file_operations.resolve_path", return_value=tmp_path),
            patch("file_organizer.web.file_operations.validate_depth"),
            patch("file_organizer.web.file_operations.list_tree_nodes", return_value=[node]),
        ):
            context = build_tree_context(str(tmp_path), settings, depth=2, active=str(tmp_path))

        assert context["nodes"] == [node]
        assert context["depth"] == 2


class TestGenerateThumbnail:
    def test_missing_file_raises_api_error(self, settings: ApiSettings) -> None:
        missing = Path("/missing")
        with patch("file_organizer.web.file_operations.resolve_path", return_value=missing):
            with pytest.raises(ApiError, match="File not found"):
                generate_thumbnail(str(missing), "file", settings)

    def test_non_image_kinds_use_placeholder(self, tmp_path: Path, settings: ApiSettings) -> None:
        target = tmp_path / "doc.pdf"
        target.write_bytes(b"pdf")
        with (
            patch("file_organizer.web.file_operations.resolve_path", return_value=target),
            patch(
                "file_organizer.web.file_operations.render_placeholder_thumbnail",
                return_value=b"thumb",
            ) as mock_placeholder,
        ):
            result = generate_thumbnail(str(target), "pdf", settings)

        assert result == b"thumb"
        mock_placeholder.assert_called_once()

    def test_large_image_uses_placeholder(self, tmp_path: Path, settings: ApiSettings) -> None:
        target = tmp_path / "photo.png"
        target.write_bytes(b"img")
        fake_stat = SimpleNamespace(st_size=20 * 1024 * 1024)
        with (
            patch("file_organizer.web.file_operations.resolve_path", return_value=target),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "stat", return_value=fake_stat),
            patch(
                "file_organizer.web.file_operations.render_placeholder_thumbnail",
                return_value=b"thumb",
            ) as mock_placeholder,
        ):
            result = generate_thumbnail(str(target), "image", settings)

        assert result == b"thumb"
        mock_placeholder.assert_called_once()

    def test_small_image_uses_renderer(self, tmp_path: Path, settings: ApiSettings) -> None:
        target = tmp_path / "photo.png"
        target.write_bytes(b"img")
        fake_stat = SimpleNamespace(st_size=5)
        with (
            patch("file_organizer.web.file_operations.resolve_path", return_value=target),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "stat", return_value=fake_stat),
            patch("file_organizer.web.file_operations.render_image_thumbnail", return_value=b"img"),
        ):
            result = generate_thumbnail(str(target), "image", settings)

        assert result == b"img"


class TestBuildPreviewContext:
    def test_missing_file_sets_error(self, settings: ApiSettings) -> None:
        with patch(
            "file_organizer.web.file_operations.resolve_path",
            side_effect=ApiError(status_code=404, error="not_found", message="File not found"),
        ):
            context = build_preview_context("/missing", settings)

        assert context["error_message"] == "File not found"

    def test_text_file_reads_preview(self, tmp_path: Path, settings: ApiSettings) -> None:
        target = tmp_path / "notes.txt"
        target.write_text("hello world")
        info = SimpleNamespace(path=str(target), size=11, modified=MagicMock())
        with (
            patch("file_organizer.web.file_operations.resolve_path", return_value=target),
            patch("file_organizer.web.file_operations.file_info_from_path", return_value=info),
            patch("file_organizer.web.file_operations.detect_kind", return_value="text"),
            patch("file_organizer.web.file_operations.is_probably_text", return_value=True),
            patch("file_organizer.web.file_operations.format_bytes", return_value="11 B"),
            patch("file_organizer.web.file_operations.format_timestamp", return_value="now"),
        ):
            context = build_preview_context(str(target), settings)

        assert context["preview_kind"] == "text"
        assert context["preview_text"] == "hello world"
        assert context["size_display"] == "11 B"

    def test_non_text_preview_downgrades_kind(self, tmp_path: Path, settings: ApiSettings) -> None:
        target = tmp_path / "notes.txt"
        target.write_text("hello world")
        info = SimpleNamespace(path=str(target), size=11, modified=MagicMock())
        with (
            patch("file_organizer.web.file_operations.resolve_path", return_value=target),
            patch("file_organizer.web.file_operations.file_info_from_path", return_value=info),
            patch("file_organizer.web.file_operations.detect_kind", return_value="text"),
            patch("file_organizer.web.file_operations.is_probably_text", return_value=False),
            patch("file_organizer.web.file_operations.format_bytes", return_value="11 B"),
            patch("file_organizer.web.file_operations.format_timestamp", return_value="now"),
        ):
            context = build_preview_context(str(target), settings)

        assert context["preview_kind"] == "file"


class TestProcessFileUploads:
    def _upload(self, name: str, data: bytes):
        return SimpleNamespace(filename=name, file=io.BytesIO(data))

    def test_process_file_uploads_saves_successful_upload(self, tmp_path: Path) -> None:
        saved, errors = process_file_uploads([self._upload("report.txt", b"hello")], tmp_path)

        assert saved == 1
        assert errors == []
        assert (tmp_path / "report.txt").read_bytes() == b"hello"

    def test_process_file_uploads_skips_invalid_filename(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.web.file_validators.validate_upload_filename",
            side_effect=ApiError(status_code=400, error="bad", message="bad name"),
        ):
            saved, errors = process_file_uploads([self._upload("bad.txt", b"hello")], tmp_path)

        assert saved == 0
        assert errors == ["bad name"]

    def test_process_file_uploads_rejects_unsanitized_name(self, tmp_path: Path) -> None:
        with patch("file_organizer.web.file_operations.sanitize_upload_name", return_value=None):
            saved, errors = process_file_uploads([self._upload("bad.txt", b"hello")], tmp_path)

        assert saved == 0
        assert "invalid filename" in errors[0]

    def test_process_file_uploads_rejects_existing_destination(self, tmp_path: Path) -> None:
        existing = tmp_path / "report.txt"
        existing.write_text("hello")

        saved, errors = process_file_uploads([self._upload("report.txt", b"new")], tmp_path)

        assert saved == 0
        assert "File already exists" in errors[0]

    def test_process_file_uploads_cleans_up_oversized_file(self, tmp_path: Path) -> None:
        with patch(
            "file_organizer.web.file_validators.validate_file_size",
            side_effect=ApiError(status_code=400, error="file_too_large", message="too large"),
        ):
            saved, errors = process_file_uploads([self._upload("big.bin", b"hello")], tmp_path)

        assert saved == 0
        assert errors == ["big.bin exceeds upload size limit."]
        assert not (tmp_path / "big.bin").exists()
