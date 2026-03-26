"""Coverage tests for file_organizer.web.files_routes — route handler branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.exceptions import ApiError

pytestmark = [pytest.mark.unit, pytest.mark.ci]


@pytest.fixture()
def mock_templates():
    """Patch the Jinja templates object."""
    response = MagicMock()
    response.headers = {}
    with patch("file_organizer.web.files_routes.templates") as tmpl:
        tmpl.TemplateResponse.return_value = response
        yield tmpl


@pytest.fixture()
def settings(tmp_path):
    s = MagicMock(spec=ApiSettings)
    s.allowed_paths = [str(tmp_path)]
    s.app_name = "File Organizer"
    s.version = "2.0.0"
    return s


class TestFilesBrowserRoute:
    """Covers the files_browser route handler."""

    def test_files_browser(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_browser

        request = MagicMock()
        results_ctx = {
            "current_path": str(tmp_path),
            "current_path_param": str(tmp_path),
            "request": request,
        }
        with (
            patch("file_organizer.web._helpers.base_context", return_value={"request": request}),
            patch(
                "file_organizer.web.files_routes._build_file_results_context",
                return_value=results_ctx,
            ),
        ):
            files_browser(
                request,
                settings,
                path=str(tmp_path),
                view="grid",
                q="",
                file_type="all",
                sort_by="name",
                sort_order="asc",
                limit=50,
            )
        mock_templates.TemplateResponse.assert_called_once()


class TestFilesListRoute:
    """Covers the files_list route handler."""

    def test_files_list(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_list

        request = MagicMock()
        results_ctx = {"request": request, "entries": [], "current_path": ""}
        with patch(
            "file_organizer.web.files_routes._build_file_results_context", return_value=results_ctx
        ):
            files_list(
                request,
                settings,
                path=str(tmp_path),
                view="grid",
                q="",
                file_type="all",
                sort_by="name",
                sort_order="asc",
                limit=50,
            )
        mock_templates.TemplateResponse.assert_called_once()


class TestFilesTreeRoute:
    """Covers the files_tree route handler."""

    def test_tree_no_path(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_tree

        request = MagicMock()
        with patch("file_organizer.web.files_routes.allowed_roots", return_value=[tmp_path]):
            files_tree(request, settings, path=None, depth=0, active=None)
        mock_templates.TemplateResponse.assert_called_once()

    def test_tree_with_path(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_tree

        (tmp_path / "subdir").mkdir()
        request = MagicMock()
        with (
            patch("file_organizer.web.files_routes.allowed_roots", return_value=[tmp_path]),
            patch("file_organizer.web.files_routes.resolve_path", return_value=tmp_path),
            patch("file_organizer.web.files_routes.validate_depth"),
        ):
            files_tree(request, settings, path=str(tmp_path), depth=1, active=str(tmp_path))
        mock_templates.TemplateResponse.assert_called_once()

    def test_tree_api_error(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_tree

        request = MagicMock()
        with (
            patch("file_organizer.web.files_routes.allowed_roots", return_value=[tmp_path]),
            patch(
                "file_organizer.web.files_routes.resolve_path",
                side_effect=ApiError(status_code=403, error="forbidden", message="nope"),
            ),
        ):
            files_tree(request, settings, path="bad", depth=0, active=None)
        mock_templates.TemplateResponse.assert_called_once()

    def test_tree_os_error(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_tree

        gone = tmp_path / "gone"
        request = MagicMock()
        with (
            patch("file_organizer.web.files_routes.allowed_roots", return_value=[tmp_path]),
            patch("file_organizer.web.files_routes.resolve_path", return_value=gone),
            patch("file_organizer.web.files_routes.validate_depth"),
        ):
            files_tree(request, settings, path=str(gone), depth=0, active=None)
        mock_templates.TemplateResponse.assert_called_once()
        ctx = mock_templates.TemplateResponse.call_args[0][2]
        assert ctx.get("error_message") is not None
        assert "gone" in ctx["error_message"]

    def test_tree_no_roots(self, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_tree

        request = MagicMock()
        with patch("file_organizer.web.files_routes.allowed_roots", return_value=[]):
            files_tree(request, settings, path=None, depth=0, active=None)
        mock_templates.TemplateResponse.assert_called_once()


class TestFilesThumbnailRoute:
    """Covers the files_thumbnail route handler."""

    def test_thumbnail_image(self, tmp_path, settings) -> None:
        from file_organizer.web.files_routes import files_thumbnail

        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 100)
        with (
            patch("file_organizer.web.files_routes.resolve_path", return_value=img),
            patch(
                "file_organizer.web.files_routes.render_image_thumbnail", return_value=b"png-data"
            ),
        ):
            resp = files_thumbnail(settings, path=str(img), kind="image")
        assert resp.media_type == "image/png"

    def test_thumbnail_image_too_large(self, tmp_path, settings) -> None:
        from file_organizer.web.files_routes import files_thumbnail

        img = tmp_path / "big.png"
        img.write_bytes(b"\x00" * 100)
        with (
            patch("file_organizer.web.files_routes.resolve_path", return_value=img),
            patch("file_organizer.web.files_routes.MAX_THUMBNAIL_BYTES", 10),
            patch(
                "file_organizer.web.files_routes.render_placeholder_thumbnail",
                return_value=b"placeholder",
            ),
        ):
            resp = files_thumbnail(settings, path=str(img), kind="image")
        assert resp.media_type == "image/png"

    def test_thumbnail_pdf(self, tmp_path, settings) -> None:
        from file_organizer.web.files_routes import files_thumbnail

        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF")
        with (
            patch("file_organizer.web.files_routes.resolve_path", return_value=pdf),
            patch(
                "file_organizer.web.files_routes.render_placeholder_thumbnail",
                return_value=b"placeholder",
            ),
        ):
            resp = files_thumbnail(settings, path=str(pdf), kind="pdf")
        assert resp.media_type == "image/png"

    def test_thumbnail_video(self, tmp_path, settings) -> None:
        from file_organizer.web.files_routes import files_thumbnail

        vid = tmp_path / "test.mp4"
        vid.write_bytes(b"\x00" * 10)
        with (
            patch("file_organizer.web.files_routes.resolve_path", return_value=vid),
            patch(
                "file_organizer.web.files_routes.render_placeholder_thumbnail",
                return_value=b"placeholder",
            ),
        ):
            resp = files_thumbnail(settings, path=str(vid), kind="video")
        assert resp.media_type == "image/png"

    def test_thumbnail_file_not_found(self, tmp_path, settings) -> None:
        from file_organizer.web.files_routes import files_thumbnail

        missing = tmp_path / "gone.txt"
        with (
            patch("file_organizer.web.files_routes.resolve_path", return_value=missing),
            pytest.raises(ApiError) as exc_info,
        ):
            files_thumbnail(settings, path=str(missing), kind="file")
        assert exc_info.value.status_code == 404

    def test_thumbnail_unknown_kind(self, tmp_path, settings) -> None:
        from file_organizer.web.files_routes import files_thumbnail

        f = tmp_path / "test.xyz"
        f.write_bytes(b"\x00")
        with (
            patch("file_organizer.web.files_routes.resolve_path", return_value=f),
            patch(
                "file_organizer.web.files_routes.render_placeholder_thumbnail",
                return_value=b"placeholder",
            ),
        ):
            resp = files_thumbnail(settings, path=str(f), kind="other")
        assert resp.media_type == "image/png"

    def test_thumbnail_image_stat_error(self, tmp_path, settings) -> None:
        from file_organizer.web.files_routes import files_thumbnail

        img = tmp_path / "bad.png"
        img.write_bytes(b"\x89PNG")

        original_stat = Path.stat

        def _stat_side_effect(self_, *a, **kw):
            if self_ == img:
                raise OSError("denied")
            return original_stat(self_, *a, **kw)

        original_exists = Path.exists
        original_is_file = Path.is_file

        def _exists_side_effect(self_, *a, **kw):
            if self_ == img:
                return True
            return original_exists(self_, *a, **kw)

        def _is_file_side_effect(self_, *a, **kw):
            if self_ == img:
                return True
            return original_is_file(self_, *a, **kw)

        with (
            patch("file_organizer.web.files_routes.resolve_path", return_value=img),
            patch.object(Path, "exists", _exists_side_effect),
            patch.object(Path, "is_file", _is_file_side_effect),
            patch.object(Path, "stat", _stat_side_effect),
            patch(
                "file_organizer.web.files_routes.render_placeholder_thumbnail",
                return_value=b"placeholder",
            ),
        ):
            resp = files_thumbnail(settings, path=str(img), kind="image")
        assert resp.media_type == "image/png"


class TestFilesRawRoute:
    """Covers the files_raw route handler."""

    def test_raw_inline(self, tmp_path, settings) -> None:
        from file_organizer.web.files_routes import files_raw

        f = tmp_path / "test.txt"
        f.write_text("hello")
        with patch("file_organizer.web.files_routes.resolve_path", return_value=f):
            resp = files_raw(settings, path=str(f), download=False)
        assert "Content-Disposition" not in resp.headers

    def test_raw_download(self, tmp_path, settings) -> None:
        from file_organizer.web.files_routes import files_raw

        f = tmp_path / "test.txt"
        f.write_text("hello")
        with patch("file_organizer.web.files_routes.resolve_path", return_value=f):
            resp = files_raw(settings, path=str(f), download=True)
        assert "Content-Disposition" in resp.headers

    def test_raw_not_found(self, tmp_path, settings) -> None:
        from file_organizer.web.files_routes import files_raw

        missing = tmp_path / "gone.txt"
        with (
            patch("file_organizer.web.files_routes.resolve_path", return_value=missing),
            pytest.raises(ApiError) as exc_info,
        ):
            files_raw(settings, path=str(missing), download=False)
        assert exc_info.value.status_code == 404


class TestFilesPreviewRoute:
    """Covers the files_preview route handler."""

    def test_preview_text_file(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_preview

        f = tmp_path / "test.txt"
        f.write_text("hello world")
        request = MagicMock()
        with (
            patch("file_organizer.web.files_routes.resolve_path", return_value=f),
            patch("file_organizer.web.files_routes.detect_kind", return_value="text"),
            patch("file_organizer.web.files_routes.is_probably_text", return_value=True),
        ):
            files_preview(request, settings, path=str(f))
        mock_templates.TemplateResponse.assert_called_once()

    def test_preview_non_text(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_preview

        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00" * 10)
        request = MagicMock()
        with (
            patch("file_organizer.web.files_routes.resolve_path", return_value=f),
            patch("file_organizer.web.files_routes.detect_kind", return_value="text"),
            patch("file_organizer.web.files_routes.is_probably_text", return_value=False),
        ):
            files_preview(request, settings, path=str(f))
        mock_templates.TemplateResponse.assert_called_once()

    def test_preview_api_error(self, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_preview

        request = MagicMock()
        with patch(
            "file_organizer.web.files_routes.resolve_path",
            side_effect=ApiError(status_code=403, error="forbidden", message="nope"),
        ):
            files_preview(request, settings, path="bad")
        mock_templates.TemplateResponse.assert_called_once()


class TestFilesUploadRoute:
    """Covers the files_upload route handler."""

    def test_upload_no_files(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_upload

        request = MagicMock()
        with (
            patch("file_organizer.web.files_routes.resolve_selected_path", return_value=tmp_path),
            patch("file_organizer.web.files_routes.allowed_roots", return_value=[tmp_path]),
            patch("file_organizer.web.files_routes.validate_depth"),
        ):
            files_upload(
                request,
                settings,
                path=str(tmp_path),
                view="grid",
                q="",
                file_type="all",
                sort_by="name",
                sort_order="asc",
                limit=50,
                files=[],
            )
        mock_templates.TemplateResponse.assert_called_once()

    def test_upload_success(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_upload

        request = MagicMock()
        upload = MagicMock()
        upload.filename = "test.txt"
        upload.file.read.side_effect = [b"hello", b""]

        with (
            patch("file_organizer.web.files_routes.resolve_selected_path", return_value=tmp_path),
            patch("file_organizer.web.files_routes.allowed_roots", return_value=[tmp_path]),
            patch("file_organizer.web.files_routes.validate_depth"),
            patch("file_organizer.web.files_routes.sanitize_upload_name", return_value="test.txt"),
        ):
            files_upload(
                request,
                settings,
                path=str(tmp_path),
                view="grid",
                q="",
                file_type="all",
                sort_by="name",
                sort_order="asc",
                limit=50,
                files=[upload],
            )
        mock_templates.TemplateResponse.assert_called_once()

    def test_upload_hidden_file_rejected(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_upload

        request = MagicMock()
        upload = MagicMock()
        upload.filename = ".hidden"

        with (
            patch("file_organizer.web.files_routes.resolve_selected_path", return_value=tmp_path),
            patch("file_organizer.web.files_routes.allowed_roots", return_value=[tmp_path]),
            patch("file_organizer.web.files_routes.validate_depth"),
        ):
            files_upload(
                request,
                settings,
                path=str(tmp_path),
                view="grid",
                q="",
                file_type="all",
                sort_by="name",
                sort_order="asc",
                limit=50,
                files=[upload],
            )
        mock_templates.TemplateResponse.assert_called_once()

    def test_upload_existing_file_skipped(self, tmp_path, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_upload

        (tmp_path / "existing.txt").write_text("old")
        request = MagicMock()
        upload = MagicMock()
        upload.filename = "existing.txt"

        with (
            patch("file_organizer.web.files_routes.resolve_selected_path", return_value=tmp_path),
            patch("file_organizer.web.files_routes.allowed_roots", return_value=[tmp_path]),
            patch("file_organizer.web.files_routes.validate_depth"),
            patch(
                "file_organizer.web.files_routes.sanitize_upload_name", return_value="existing.txt"
            ),
        ):
            files_upload(
                request,
                settings,
                path=str(tmp_path),
                view="grid",
                q="",
                file_type="all",
                sort_by="name",
                sort_order="asc",
                limit=50,
                files=[upload],
            )
        mock_templates.TemplateResponse.assert_called_once()

    def test_upload_no_target_dir(self, settings, mock_templates) -> None:
        from file_organizer.web.files_routes import files_upload

        request = MagicMock()
        with (
            patch("file_organizer.web.files_routes.resolve_selected_path", return_value=None),
            patch("file_organizer.web.files_routes.allowed_roots", return_value=[]),
            patch("file_organizer.web.files_routes.validate_depth"),
        ):
            files_upload(
                request,
                settings,
                path="",
                view="grid",
                q="",
                file_type="all",
                sort_by="name",
                sort_order="asc",
                limit=50,
                files=[],
            )
        mock_templates.TemplateResponse.assert_called_once()
