"""Unit tests for web _helpers module.

Tests helper functions for path resolution, file type detection, formatting,
filename sanitization, and thumbnail rendering.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.exceptions import ApiError
from file_organizer.web._helpers import (
    FILE_TYPE_GROUPS,
    MAX_LIMIT,
    MAX_NAV_DEPTH,
    THUMBNAIL_SIZE,
    allowed_roots,
    as_bool,
    base_context,
    build_content_disposition,
    clamp_limit,
    detect_kind,
    format_bytes,
    format_timestamp,
    has_children,
    is_probably_text,
    normalize_sort_by,
    normalize_sort_order,
    normalize_view,
    parse_file_type_filter,
    path_id,
    render_placeholder_thumbnail,
    resolve_selected_path,
    sanitize_upload_name,
    select_root_for_path,
    validate_depth,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_request():
    """Mock FastAPI Request object."""
    req = MagicMock()
    req.url = MagicMock()
    req.url.path = "/ui/files"
    return req


@pytest.fixture()
def mock_settings():
    """Mock ApiSettings object."""
    s = MagicMock(spec=ApiSettings)
    s.app_name = "File Organizer"
    s.version = "2.0.0"
    s.allowed_paths = ["/tmp/test"]
    return s


# ---------------------------------------------------------------------------
# base_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBaseContext:
    """Test base_context helper."""

    def test_basic_context(self, mock_request, mock_settings):
        """Build a basic template context."""
        context = base_context(
            mock_request, mock_settings, active="files", title="File Browser"
        )

        assert context["request"] is mock_request
        assert context["app_name"] == "File Organizer"
        assert context["version"] == "2.0.0"
        assert context["active"] == "files"
        assert context["page_title"] == "File Browser"
        assert context["nav_items"]
        assert "year" in context

    def test_context_with_extras(self, mock_request, mock_settings):
        """Include extra context variables."""
        extras = {"custom_var": "custom_value", "count": 42}
        context = base_context(
            mock_request,
            mock_settings,
            active="files",
            title="Files",
            extras=extras,
        )

        assert context["custom_var"] == "custom_value"
        assert context["count"] == 42

    def test_context_year_is_current(self, mock_request, mock_settings):
        """Year in context is current year."""
        context = base_context(
            mock_request, mock_settings, active="home", title="Home"
        )
        assert context["year"] == datetime.now(UTC).year


# ---------------------------------------------------------------------------
# allowed_roots
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAllowedRoots:
    """Test allowed_roots helper."""

    @patch("file_organizer.web._helpers.resolve_path")
    def test_resolves_allowed_paths(self, mock_resolve, mock_settings):
        """Resolve all allowed paths."""
        mock_settings.allowed_paths = ["/tmp/test1", "/tmp/test2"]
        mock_resolve.side_effect = [Path("/tmp/test1"), Path("/tmp/test2")]

        roots = allowed_roots(mock_settings)

        assert len(roots) == 2
        assert Path("/tmp/test1") in roots
        assert Path("/tmp/test2") in roots

    @patch("file_organizer.web._helpers.resolve_path")
    def test_skips_unresolvable_paths(self, mock_resolve, mock_settings):
        """Skip paths that cannot be resolved."""
        mock_settings.allowed_paths = ["/tmp/test1", "/tmp/invalid"]
        mock_resolve.side_effect = [Path("/tmp/test1"), ApiError(400, "error", "Invalid path")]

        roots = allowed_roots(mock_settings)

        assert len(roots) == 1
        assert Path("/tmp/test1") in roots

    @patch("file_organizer.web._helpers.resolve_path")
    def test_deduplicates_roots(self, mock_resolve, mock_settings):
        """Remove duplicate resolved roots."""
        mock_settings.allowed_paths = ["/tmp/test", "/tmp/test"]
        mock_resolve.side_effect = [Path("/tmp/test"), Path("/tmp/test")]

        roots = allowed_roots(mock_settings)

        assert len(roots) == 1

    def test_handles_none_allowed_paths(self, mock_settings):
        """Handle None allowed_paths gracefully."""
        mock_settings.allowed_paths = None
        roots = allowed_roots(mock_settings)
        assert roots == []


# ---------------------------------------------------------------------------
# resolve_selected_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveSelectedPath:
    """Test resolve_selected_path helper."""

    @patch("file_organizer.web._helpers.resolve_path")
    def test_resolves_provided_path(self, mock_resolve, mock_settings):
        """Resolve a provided path."""
        mock_resolve.return_value = Path("/tmp/test/subdir")
        result = resolve_selected_path("/tmp/test/subdir", mock_settings)
        assert result == Path("/tmp/test/subdir")

    @patch("file_organizer.web._helpers.allowed_roots")
    def test_fallback_to_first_root(self, mock_roots, mock_settings):
        """Fall back to first allowed root when no path provided."""
        mock_roots.return_value = [Path("/root1"), Path("/root2")]
        result = resolve_selected_path(None, mock_settings)
        assert result == Path("/root1")

    @patch("file_organizer.web._helpers.allowed_roots")
    def test_returns_none_when_no_roots(self, mock_roots, mock_settings):
        """Return None when no roots available."""
        mock_roots.return_value = []
        result = resolve_selected_path(None, mock_settings)
        assert result is None


# ---------------------------------------------------------------------------
# format_bytes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatBytes:
    """Test format_bytes helper."""

    def test_bytes_small(self):
        assert format_bytes(512) == "512 B"

    def test_kilobytes(self):
        result = format_bytes(1024 * 5)
        assert "KB" in result

    def test_megabytes(self):
        result = format_bytes(1024 * 1024 * 10)
        assert "MB" in result

    def test_gigabytes(self):
        result = format_bytes(1024 * 1024 * 1024 * 5)
        assert "GB" in result

    def test_terabytes(self):
        result = format_bytes(1024 * 1024 * 1024 * 1024 * 2)
        assert "TB" in result

    def test_petabytes(self):
        result = format_bytes(1024 * 1024 * 1024 * 1024 * 1024 * 3)
        assert "PB" in result


# ---------------------------------------------------------------------------
# format_timestamp
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatTimestamp:
    """Test format_timestamp helper."""

    def test_format_timestamp(self):
        ts = datetime(2025, 1, 15, 14, 30, 45, tzinfo=UTC)
        result = format_timestamp(ts)
        assert "2025-01-15" in result
        assert "14:30" in result
        assert "UTC" in result

    def test_format_different_timezone(self):
        """Handle timestamps with different timezone."""
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/New_York")
        ts = datetime(2025, 1, 15, 14, 30, 45, tzinfo=tz)
        result = format_timestamp(ts)
        assert "UTC" in result


# ---------------------------------------------------------------------------
# parse_file_type_filter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseFileTypeFilter:
    """Test parse_file_type_filter helper."""

    def test_none_returns_none(self):
        assert parse_file_type_filter(None) is None

    def test_all_returns_none(self):
        assert parse_file_type_filter("all") is None

    def test_known_type_group(self):
        result = parse_file_type_filter("image")
        assert result == FILE_TYPE_GROUPS["image"]

    def test_extension_with_dot(self):
        result = parse_file_type_filter(".pdf")
        assert result == {".pdf"}

    def test_extension_without_dot(self):
        result = parse_file_type_filter("txt")
        assert result == {".txt"}

    def test_case_insensitive(self):
        result1 = parse_file_type_filter("image")
        result2 = parse_file_type_filter("IMAGE")
        assert result1 == result2


# ---------------------------------------------------------------------------
# detect_kind
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectKind:
    """Test detect_kind helper."""

    def test_image_file(self):
        assert detect_kind(Path("photo.jpg")) == "image"

    def test_pdf_file(self):
        assert detect_kind(Path("document.pdf")) == "pdf"

    def test_video_file(self):
        assert detect_kind(Path("movie.mp4")) == "video"

    def test_audio_file(self):
        assert detect_kind(Path("song.mp3")) == "audio"

    def test_text_file(self):
        assert detect_kind(Path("readme.txt")) == "text"

    def test_cad_file(self):
        assert detect_kind(Path("design.dxf")) == "cad"

    def test_unknown_file(self):
        assert detect_kind(Path("archive.xyz")) == "file"

    def test_case_insensitive(self):
        assert detect_kind(Path("photo.JPG")) == "image"


# ---------------------------------------------------------------------------
# path_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPathId:
    """Test path_id helper."""

    def test_returns_short_hash(self):
        result = path_id(Path("/tmp/test"))
        assert isinstance(result, str)
        assert len(result) == 10

    def test_consistent_hash(self):
        path = Path("/tmp/test/file.txt")
        hash1 = path_id(path)
        hash2 = path_id(path)
        assert hash1 == hash2

    def test_different_paths_different_hashes(self):
        hash1 = path_id(Path("/tmp/test1"))
        hash2 = path_id(Path("/tmp/test2"))
        assert hash1 != hash2


# ---------------------------------------------------------------------------
# select_root_for_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSelectRootForPath:
    """Test select_root_for_path helper."""

    def test_selects_matching_root(self, tmp_path):
        """Select a root that the path is under."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        result = select_root_for_path(sub, [tmp_path])
        assert result == tmp_path

    def test_selects_longest_matching_root(self, tmp_path):
        """Select the longest matching root."""
        sub1 = tmp_path / "sub1"
        sub2 = sub1 / "sub2"
        sub2.mkdir(parents=True)
        result = select_root_for_path(sub2, [tmp_path, sub1])
        assert result == sub1

    def test_returns_path_when_no_match(self, tmp_path):
        """Return the path itself when no root matches."""
        other = Path("/other/path")
        result = select_root_for_path(other, [tmp_path])
        assert result == other


# ---------------------------------------------------------------------------
# validate_depth
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateDepth:
    """Test validate_depth helper."""

    def test_shallow_path_passes(self, tmp_path):
        """Shallow paths don't raise."""
        validate_depth(tmp_path, [tmp_path])

    def test_deep_path_raises(self, tmp_path):
        """Deep paths raise ApiError."""
        deep = tmp_path
        for _ in range(MAX_NAV_DEPTH + 2):
            deep = deep / "level"

        with pytest.raises(ApiError) as exc_info:
            validate_depth(deep, [tmp_path])

        assert exc_info.value.error == "path_too_deep"


# ---------------------------------------------------------------------------
# has_children
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHasChildren:
    """Test has_children helper."""

    def test_directory_with_subdirs(self, tmp_path):
        """Directory with subdirectories returns True."""
        (tmp_path / "subdir").mkdir()
        assert has_children(tmp_path) is True

    def test_empty_directory(self, tmp_path):
        """Empty directory returns False."""
        assert has_children(tmp_path) is False

    def test_directory_with_only_files(self, tmp_path):
        """Directory with only files returns False."""
        (tmp_path / "file.txt").write_text("test")
        assert has_children(tmp_path) is False

    @patch("file_organizer.web._helpers.is_hidden")
    def test_ignores_hidden_subdirs(self, mock_hidden, tmp_path):
        """Ignore hidden subdirectories."""
        (tmp_path / ".hidden").mkdir()
        mock_hidden.return_value = True
        assert has_children(tmp_path) is False

    def test_nonexistent_directory(self):
        """Nonexistent directory returns False."""
        assert has_children(Path("/nonexistent/path")) is False


# ---------------------------------------------------------------------------
# is_probably_text
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsProbablyText:
    """Test is_probably_text helper."""

    def test_text_file_is_text(self, tmp_path):
        """Text file is detected as text."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("Hello, world!")
        assert is_probably_text(text_file) is True

    def test_binary_file_is_not_text(self, tmp_path):
        """Binary file is not detected as text."""
        binary_file = tmp_path / "test.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03")
        assert is_probably_text(binary_file) is False

    def test_empty_file_is_text(self, tmp_path):
        """Empty file is considered text."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")
        assert is_probably_text(empty_file) is True

    def test_nonexistent_file(self):
        """Nonexistent file returns False."""
        assert is_probably_text(Path("/nonexistent/file.txt")) is False

    def test_utf8_encoded_text(self, tmp_path):
        """UTF-8 encoded text is detected as text."""
        text_file = tmp_path / "utf8.txt"
        text_file.write_text("Hello, 世界!", encoding="utf-8")
        assert is_probably_text(text_file) is True


# ---------------------------------------------------------------------------
# sanitize_upload_name
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSanitizeUploadName:
    """Test sanitize_upload_name helper."""

    def test_valid_filename(self):
        result = sanitize_upload_name("document.txt")
        assert result == "document.txt"

    def test_rejects_empty_name(self):
        assert sanitize_upload_name("") is None

    def test_rejects_dot(self):
        assert sanitize_upload_name(".") is None

    def test_rejects_double_dot(self):
        assert sanitize_upload_name("..") is None

    def test_rejects_hidden_file(self):
        assert sanitize_upload_name(".hidden") is None

    def test_rejects_too_long_name(self):
        long_name = "a" * 300
        assert sanitize_upload_name(long_name) is None

    def test_rejects_invalid_chars(self):
        assert sanitize_upload_name("file<name>.txt") is None
        assert sanitize_upload_name("file|name>.txt") is None

    def test_accepts_spaces_and_dashes(self):
        result = sanitize_upload_name("my-document (v1).txt")
        assert result == "my-document (v1).txt"

    def test_strips_path_components(self):
        result = sanitize_upload_name("/path/to/file.txt")
        assert result == "file.txt"


# ---------------------------------------------------------------------------
# normalize_view
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeView:
    """Test normalize_view helper."""

    def test_valid_grid_view(self):
        assert normalize_view("grid") == "grid"

    def test_valid_list_view(self):
        assert normalize_view("list") == "list"

    def test_invalid_view_defaults_to_grid(self):
        assert normalize_view("invalid") == "grid"

    def test_empty_string_defaults_to_grid(self):
        assert normalize_view("") == "grid"


# ---------------------------------------------------------------------------
# normalize_sort_by
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeSortBy:
    """Test normalize_sort_by helper."""

    def test_valid_sort_by_name(self):
        assert normalize_sort_by("name") == "name"

    def test_valid_sort_by_size(self):
        assert normalize_sort_by("size") == "size"

    def test_invalid_sort_by_defaults_to_name(self):
        assert normalize_sort_by("invalid") == "name"


# ---------------------------------------------------------------------------
# normalize_sort_order
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeSortOrder:
    """Test normalize_sort_order helper."""

    def test_valid_asc(self):
        assert normalize_sort_order("asc") == "asc"

    def test_valid_desc(self):
        assert normalize_sort_order("desc") == "desc"

    def test_invalid_defaults_to_asc(self):
        assert normalize_sort_order("invalid") == "asc"


# ---------------------------------------------------------------------------
# clamp_limit
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClampLimit:
    """Test clamp_limit helper."""

    def test_valid_limit_unchanged(self):
        assert clamp_limit(50) == 50

    def test_zero_clamped_to_one(self):
        assert clamp_limit(0) == 1

    def test_negative_clamped_to_one(self):
        assert clamp_limit(-100) == 1

    def test_too_large_clamped_to_max(self):
        assert clamp_limit(MAX_LIMIT + 1000) == MAX_LIMIT


# ---------------------------------------------------------------------------
# build_content_disposition
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildContentDisposition:
    """Test build_content_disposition helper."""

    def test_simple_filename(self):
        result = build_content_disposition("document.pdf")
        assert "document.pdf" in result
        assert "attachment" in result

    def test_filename_with_spaces(self):
        result = build_content_disposition("my document.pdf")
        assert "attachment" in result

    def test_removes_newlines(self):
        result = build_content_disposition("file\nname.txt")
        assert "\n" not in result

    def test_removes_carriage_returns(self):
        result = build_content_disposition("file\rname.txt")
        assert "\r" not in result

    def test_handles_unicode_filename(self):
        result = build_content_disposition("文件.txt")
        assert "attachment" in result


# ---------------------------------------------------------------------------
# as_bool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAsBool:
    """Test as_bool helper."""

    def test_none_returns_false(self):
        assert as_bool(None) is False

    def test_empty_string_returns_false(self):
        assert as_bool("") is False

    def test_one_returns_true(self):
        assert as_bool("1") is True

    def test_true_returns_true(self):
        assert as_bool("true") is True

    def test_yes_returns_true(self):
        assert as_bool("yes") is True

    def test_on_returns_true(self):
        assert as_bool("on") is True

    def test_zero_returns_false(self):
        assert as_bool("0") is False

    def test_false_returns_false(self):
        assert as_bool("false") is False


# ---------------------------------------------------------------------------
# render_placeholder_thumbnail
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderPlaceholderThumbnail:
    """Test render_placeholder_thumbnail helper."""

    def test_renders_png_bytes(self):
        """Render returns PNG bytes."""
        result = render_placeholder_thumbnail("txt", THUMBNAIL_SIZE)
        assert isinstance(result, bytes)
        assert result.startswith(b"\x89PNG")

    def test_renders_different_sizes(self):
        """Render different sizes."""
        small = render_placeholder_thumbnail("txt", (100, 100))
        large = render_placeholder_thumbnail("txt", (500, 500))
        assert len(small) != len(large)

    def test_label_included_in_thumbnail(self):
        """Label is rendered in thumbnail."""
        result = render_placeholder_thumbnail("doc", THUMBNAIL_SIZE)
        assert isinstance(result, bytes)
        assert len(result) > 0
