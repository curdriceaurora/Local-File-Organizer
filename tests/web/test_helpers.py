"""Tests for web template helpers and utilities.

Tests verify:
- Template context is built correctly with all required variables
- Template formatting helpers work with various inputs
- File type detection and path utilities function correctly
- Form validators accept valid input and reject invalid input
- Helper functions handle edge cases (empty input, special chars, None values)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.exceptions import ApiError
from file_organizer.web._helpers import (
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
def settings(tmp_path):
    """Return an ApiSettings mock."""
    s = MagicMock(spec=ApiSettings)
    s.allowed_paths = [str(tmp_path)]
    s.app_name = "File Organizer"
    s.version = "2.0.0"
    return s


@pytest.fixture()
def mock_request():
    """Return a mock FastAPI Request."""
    req = MagicMock()
    req.url = MagicMock()
    req.url.path = "/ui/files"
    return req


@pytest.fixture()
def file_tree(tmp_path):
    """Create a sample file tree for testing."""
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "dir_b").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("hello")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "video.mp4").write_bytes(b"test")
    (tmp_path / "audio.mp3").write_bytes(b"test")
    (tmp_path / "doc.pdf").write_bytes(b"test")
    (tmp_path / "code.py").write_text("print('hello')")
    (tmp_path / "data.json").write_text('{"key": "value"}')
    (tmp_path / "dir_a" / "nested.txt").write_text("nested")
    return tmp_path


# ---------------------------------------------------------------------------
# base_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBaseContext:
    """Test template context building."""

    def test_base_context_has_required_keys(self, mock_request, settings):
        """Base context should include all required template variables."""
        ctx = base_context(mock_request, settings, active="home", title="Home")
        assert ctx["request"] == mock_request
        assert ctx["app_name"] == "File Organizer"
        assert ctx["version"] == "2.0.0"
        assert ctx["active"] == "home"
        assert ctx["page_title"] == "Home"
        assert "nav_items" in ctx
        assert "year" in ctx

    def test_base_context_with_extras(self, mock_request, settings):
        """Base context should merge extra variables."""
        extras = {"custom_var": "custom_value", "count": 42}
        ctx = base_context(
            mock_request,
            settings,
            active="test",
            title="Test",
            extras=extras,
        )
        assert ctx["custom_var"] == "custom_value"
        assert ctx["count"] == 42

    def test_nav_items_present(self, mock_request, settings):
        """Navigation items should be included."""
        ctx = base_context(mock_request, settings, active="home", title="Home")
        assert len(ctx["nav_items"]) > 0
        nav_labels = [item[0] for item in ctx["nav_items"]]
        assert "Home" in nav_labels
        assert "Settings" in nav_labels


# ---------------------------------------------------------------------------
# allowed_roots
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAllowedRoots:
    """Test allowed root path resolution."""

    def test_resolves_allowed_paths(self, file_tree):
        """Should return resolved allowed paths."""
        settings = MagicMock(spec=ApiSettings)
        settings.allowed_paths = [str(file_tree)]
        roots = allowed_roots(settings)
        assert len(roots) == 1
        assert roots[0] == file_tree

    def test_no_allowed_paths(self):
        """Should return empty list when no paths allowed."""
        settings = MagicMock(spec=ApiSettings)
        settings.allowed_paths = None
        roots = allowed_roots(settings)
        assert roots == []

    def test_empty_allowed_paths(self):
        """Should return empty list when paths list is empty."""
        settings = MagicMock(spec=ApiSettings)
        settings.allowed_paths = []
        roots = allowed_roots(settings)
        assert roots == []


# ---------------------------------------------------------------------------
# resolve_selected_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveSelectedPath:
    """Test user path resolution."""

    def test_valid_path_in_allowed_roots(self, file_tree):
        """Should resolve path when in allowed roots."""
        settings = MagicMock(spec=ApiSettings)
        settings.allowed_paths = [str(file_tree)]
        result = resolve_selected_path(str(file_tree / "dir_a"), settings)
        assert result == file_tree / "dir_a"

    def test_none_path_returns_first_root(self, file_tree):
        """Should return first allowed root when path is None."""
        settings = MagicMock(spec=ApiSettings)
        settings.allowed_paths = [str(file_tree)]
        result = resolve_selected_path(None, settings)
        assert result == file_tree

    def test_empty_path_returns_first_root(self, file_tree):
        """Should return first allowed root when path is empty."""
        settings = MagicMock(spec=ApiSettings)
        settings.allowed_paths = [str(file_tree)]
        result = resolve_selected_path("", settings)
        assert result == file_tree


# ---------------------------------------------------------------------------
# format_bytes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatBytes:
    """Test byte formatting."""

    def test_bytes_under_1kb(self):
        """Should format bytes correctly."""
        assert format_bytes(0) == "0 B"
        assert format_bytes(512) == "512 B"
        assert format_bytes(1023) == "1023 B"

    def test_kilobytes(self):
        """Should format kilobytes correctly."""
        assert "KB" in format_bytes(1024)
        assert "1.0 KB" == format_bytes(1024)
        assert "10.0 KB" == format_bytes(10 * 1024)

    def test_megabytes(self):
        """Should format megabytes correctly."""
        result = format_bytes(5 * 1024 * 1024)
        assert "MB" in result
        assert "5.0 MB" == result

    def test_gigabytes(self):
        """Should format gigabytes correctly."""
        result = format_bytes(2 * 1024 * 1024 * 1024)
        assert "GB" in result
        assert "2.0 GB" == result

    def test_terabytes(self):
        """Should format terabytes correctly."""
        result = format_bytes(1024 * 1024 * 1024 * 1024)
        assert "TB" in result


# ---------------------------------------------------------------------------
# format_timestamp
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatTimestamp:
    """Test timestamp formatting."""

    def test_format_timestamp(self):
        """Should format datetime correctly."""
        dt = datetime(2025, 1, 15, 14, 30, 45, tzinfo=UTC)
        result = format_timestamp(dt)
        assert "2025-01-15" in result
        assert "14:30" in result
        assert "UTC" in result

    def test_format_timestamp_structure(self):
        """Should follow expected format."""
        dt = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)
        result = format_timestamp(dt)
        # Format: "YYYY-MM-DD HH:MM UTC"
        parts = result.split()
        assert len(parts) == 3
        assert "-" in parts[0]  # Date part
        assert ":" in parts[1]  # Time part
        assert parts[2] == "UTC"


# ---------------------------------------------------------------------------
# parse_file_type_filter
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseFileTypeFilter:
    """Test file type filter parsing."""

    def test_none_filter(self):
        """None should return None (all files)."""
        assert parse_file_type_filter(None) is None

    def test_all_filter(self):
        """'all' should return None (all files)."""
        assert parse_file_type_filter("all") is None

    def test_image_group(self):
        """Should parse image group correctly."""
        result = parse_file_type_filter("image")
        assert isinstance(result, set)
        assert ".jpg" in result or ".png" in result

    def test_video_group(self):
        """Should parse video group correctly."""
        result = parse_file_type_filter("video")
        assert isinstance(result, set)
        assert len(result) > 0

    def test_custom_extension(self):
        """Should parse custom extensions."""
        assert parse_file_type_filter(".pdf") == {".pdf"}
        assert parse_file_type_filter("pdf") == {".pdf"}

    def test_case_insensitive(self):
        """Should be case insensitive."""
        result1 = parse_file_type_filter("IMAGE")
        result2 = parse_file_type_filter("image")
        assert result1 == result2


# ---------------------------------------------------------------------------
# detect_kind
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectKind:
    """Test file kind detection."""

    def test_image_detection(self):
        """Should detect images correctly."""
        assert detect_kind(Path("photo.jpg")) == "image"
        assert detect_kind(Path("pic.png")) == "image"
        assert detect_kind(Path("img.gif")) == "image"

    def test_pdf_detection(self):
        """Should detect PDFs correctly."""
        assert detect_kind(Path("document.pdf")) == "pdf"

    def test_video_detection(self):
        """Should detect videos correctly."""
        assert detect_kind(Path("movie.mp4")) == "video"
        assert detect_kind(Path("clip.mkv")) == "video"

    def test_audio_detection(self):
        """Should detect audio files correctly."""
        assert detect_kind(Path("song.mp3")) == "audio"
        assert detect_kind(Path("track.wav")) == "audio"

    def test_text_detection(self):
        """Should detect text files correctly."""
        assert detect_kind(Path("readme.txt")) == "text"
        assert detect_kind(Path("document.docx")) == "text"
        assert detect_kind(Path("data.csv")) == "text"

    def test_cad_detection(self):
        """Should detect CAD files correctly."""
        assert detect_kind(Path("drawing.dxf")) == "cad"

    def test_default_to_file(self):
        """Should default to 'file' for unknown types."""
        assert detect_kind(Path("unknown.xyz")) == "file"
        assert detect_kind(Path("data.xyz")) == "file"

    def test_case_insensitive(self):
        """Should be case insensitive."""
        assert detect_kind(Path("photo.JPG")) == "image"
        assert detect_kind(Path("document.PDF")) == "pdf"


# ---------------------------------------------------------------------------
# path_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPathId:
    """Test path identifier generation."""

    def test_returns_string(self):
        """Should return a 10-character hex string."""
        result = path_id(Path("/tmp/test"))
        assert isinstance(result, str) and len(result) == 10

    def test_returns_short_hash(self):
        """Should return a 10-character hash."""
        result = path_id(Path("/tmp/test"))
        assert len(result) == 10

    def test_same_path_same_id(self):
        """Same path should produce same ID."""
        path = Path("/tmp/test")
        id1 = path_id(path)
        id2 = path_id(path)
        assert id1 == id2

    def test_different_paths_different_ids(self):
        """Different paths should produce different IDs."""
        id1 = path_id(Path("/tmp/test1"))
        id2 = path_id(Path("/tmp/test2"))
        assert id1 != id2


# ---------------------------------------------------------------------------
# select_root_for_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSelectRootForPath:
    """Test root selection for paths."""

    def test_selects_matching_root(self, file_tree):
        """Should select matching root."""
        roots = [file_tree]
        path = file_tree / "dir_a"
        result = select_root_for_path(path, roots)
        assert result == file_tree

    def test_selects_longest_matching_root(self, file_tree):
        """Should select longest matching root."""
        root1 = file_tree
        root2 = file_tree / "dir_a"
        root2.mkdir(exist_ok=True)
        roots = [root1, root2]
        path = root2 / "file.txt"
        result = select_root_for_path(path, roots)
        assert result == root2

    def test_returns_path_when_no_match(self, file_tree):
        """Should return path when no root matches."""
        roots = [Path("/other/path")]
        path = file_tree / "dir_a"
        result = select_root_for_path(path, roots)
        assert result == path


# ---------------------------------------------------------------------------
# validate_depth
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateDepth:
    """Test depth validation."""

    def test_shallow_path_valid(self, file_tree):
        """Shallow paths should be valid."""
        path = file_tree / "dir_a"
        # Should not raise
        validate_depth(path, [file_tree])

    def test_deeply_nested_path_valid(self, file_tree):
        """Moderately nested paths should be valid."""
        deep = file_tree / "a" / "b" / "c"
        deep.mkdir(parents=True, exist_ok=True)
        # Should not raise (depth < MAX_NAV_DEPTH)
        validate_depth(deep, [file_tree])

    def test_very_deep_path_raises(self, file_tree):
        """Very deep paths should raise ApiError."""
        # Create a path deeper than MAX_NAV_DEPTH
        deep = file_tree
        for i in range(15):
            deep = deep / f"level_{i}"
        deep.mkdir(parents=True, exist_ok=True)

        with pytest.raises(ApiError) as exc_info:
            validate_depth(deep, [file_tree])
        assert exc_info.value.error == "path_too_deep"


# ---------------------------------------------------------------------------
# has_children
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHasChildren:
    """Test directory children detection."""

    def test_directory_with_subdirs(self, file_tree):
        """Should detect subdirectories."""
        assert has_children(file_tree) is True

    def test_empty_directory(self, tmp_path):
        """Empty directory should have no children."""
        empty = tmp_path / "empty"
        empty.mkdir()
        assert has_children(empty) is False

    def test_directory_with_only_files(self, file_tree):
        """Directory with only files should have no children."""
        dir_with_files = file_tree / "dir_a"
        # dir_a has a nested.txt but no subdirs
        assert has_children(dir_with_files) is False

    def test_nonexistent_directory(self):
        """Nonexistent directory should return False."""
        assert has_children(Path("/nonexistent/path")) is False

    def test_ignores_hidden_directories(self, tmp_path):
        """Should ignore hidden directories."""
        visible = tmp_path / "visible"
        visible.mkdir()
        hidden = visible / ".hidden"
        hidden.mkdir()
        assert has_children(visible) is False


# ---------------------------------------------------------------------------
# is_probably_text
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsProbablyText:
    """Test text file detection."""

    def test_text_file(self, file_tree):
        """Should detect text files."""
        txt_file = file_tree / "file.txt"
        assert is_probably_text(txt_file) is True

    def test_python_file(self, file_tree):
        """Should detect Python source files."""
        py_file = file_tree / "code.py"
        assert is_probably_text(py_file) is True

    def test_json_file(self, file_tree):
        """Should detect JSON files."""
        json_file = file_tree / "data.json"
        assert is_probably_text(json_file) is True

    def test_binary_file(self, file_tree):
        """Should reject binary files."""
        png_file = file_tree / "image.png"
        assert is_probably_text(png_file) is False

    def test_nonexistent_file(self):
        """Should return False for nonexistent files."""
        assert is_probably_text(Path("/nonexistent.txt")) is False

    def test_empty_file(self, tmp_path):
        """Should return True for empty files."""
        empty = tmp_path / "empty.txt"
        empty.write_text("")
        assert is_probably_text(empty) is True


# ---------------------------------------------------------------------------
# sanitize_upload_name
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSanitizeUploadName:
    """Test upload filename sanitization."""

    def test_valid_filename(self):
        """Should accept valid filenames."""
        assert sanitize_upload_name("document.pdf") == "document.pdf"
        assert sanitize_upload_name("photo.jpg") == "photo.jpg"
        assert sanitize_upload_name("data_2025.json") == "data_2025.json"

    def test_rejects_current_dir(self):
        """Should reject '.' as filename."""
        assert sanitize_upload_name(".") is None

    def test_rejects_parent_dir(self):
        """Should reject '..' as filename."""
        assert sanitize_upload_name("..") is None

    def test_rejects_hidden_files(self):
        """Should reject files starting with '.'."""
        assert sanitize_upload_name(".hidden") is None

    def test_rejects_invalid_chars(self):
        """Should reject filenames with invalid characters."""
        assert sanitize_upload_name('file"name.txt') is None
        assert sanitize_upload_name("file<name>.txt") is None
        assert sanitize_upload_name("file|name.txt") is None

    def test_rejects_long_names(self):
        """Should reject very long filenames."""
        long_name = "a" * 300 + ".txt"
        assert sanitize_upload_name(long_name) is None

    def test_strips_whitespace(self):
        """Should strip leading/trailing whitespace."""
        result = sanitize_upload_name("  document.pdf  ")
        assert result == "document.pdf"

    def test_rejects_empty_name(self):
        """Should reject empty names."""
        assert sanitize_upload_name("") is None
        assert sanitize_upload_name("   ") is None


# ---------------------------------------------------------------------------
# normalize_view
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeView:
    """Test view parameter normalization."""

    def test_valid_grid_view(self):
        """Should accept 'grid' view."""
        assert normalize_view("grid") == "grid"

    def test_valid_list_view(self):
        """Should accept 'list' view."""
        assert normalize_view("list") == "list"

    def test_invalid_view_defaults_to_grid(self):
        """Should default to 'grid' for invalid views."""
        assert normalize_view("invalid") == "grid"
        assert normalize_view("table") == "grid"
        assert normalize_view("") == "grid"


# ---------------------------------------------------------------------------
# normalize_sort_by
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeSortBy:
    """Test sort-by parameter normalization."""

    def test_valid_sorts(self):
        """Should accept valid sort fields."""
        assert normalize_sort_by("name") == "name"
        assert normalize_sort_by("size") == "size"
        assert normalize_sort_by("created") == "created"
        assert normalize_sort_by("modified") == "modified"
        assert normalize_sort_by("type") == "type"

    def test_invalid_sort_defaults_to_name(self):
        """Should default to 'name' for invalid sorts."""
        assert normalize_sort_by("invalid") == "name"
        assert normalize_sort_by("date") == "name"


# ---------------------------------------------------------------------------
# normalize_sort_order
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeSortOrder:
    """Test sort-order parameter normalization."""

    def test_valid_orders(self):
        """Should accept valid sort orders."""
        assert normalize_sort_order("asc") == "asc"
        assert normalize_sort_order("desc") == "desc"

    def test_invalid_order_defaults_to_asc(self):
        """Should default to 'asc' for invalid orders."""
        assert normalize_sort_order("invalid") == "asc"
        assert normalize_sort_order("ascending") == "asc"


# ---------------------------------------------------------------------------
# clamp_limit
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClampLimit:
    """Test pagination limit clamping."""

    def test_valid_limit(self):
        """Should accept valid limits."""
        assert clamp_limit(10) == 10
        assert clamp_limit(100) == 100
        assert clamp_limit(250) == 250

    def test_lower_bound(self):
        """Should clamp to minimum."""
        assert clamp_limit(0) == 1
        assert clamp_limit(-10) == 1

    def test_upper_bound(self):
        """Should clamp to maximum."""
        assert clamp_limit(1000) == 500  # MAX_LIMIT is 500


# ---------------------------------------------------------------------------
# build_content_disposition
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildContentDisposition:
    """Test Content-Disposition header building."""

    def test_simple_filename(self):
        """Should format simple filenames correctly."""
        result = build_content_disposition("document.pdf")
        assert "attachment" in result
        assert "document.pdf" in result

    def test_filename_with_spaces(self):
        """Should handle filenames with spaces."""
        result = build_content_disposition("my document.pdf")
        assert "attachment" in result
        assert "filename" in result

    def test_filename_with_special_chars(self):
        """Should handle special characters."""
        result = build_content_disposition("résumé.pdf")
        assert "attachment" in result
        assert "filename" in result

    def test_removes_newlines(self):
        """Should remove newline characters."""
        result = build_content_disposition("file\nname.txt")
        assert "\n" not in result

    def test_removes_carriage_returns(self):
        """Should remove carriage return characters."""
        result = build_content_disposition("file\rname.txt")
        assert "\r" not in result

    def test_removes_quotes(self):
        """Should handle quotes in filename."""
        result = build_content_disposition('file"name.txt')
        assert "attachment" in result


# ---------------------------------------------------------------------------
# as_bool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAsBool:
    """Test form value to boolean conversion."""

    def test_true_values(self):
        """Should recognize true values."""
        assert as_bool("1") is True
        assert as_bool("true") is True
        assert as_bool("yes") is True
        assert as_bool("on") is True
        assert as_bool("TRUE") is True
        assert as_bool("YES") is True

    def test_false_values(self):
        """Should treat non-true values as false."""
        assert as_bool("0") is False
        assert as_bool("false") is False
        assert as_bool("no") is False
        assert as_bool("off") is False
        assert as_bool("") is False

    def test_none_value(self):
        """Should treat None as false."""
        assert as_bool(None) is False

    def test_with_whitespace(self):
        """Should strip whitespace before checking."""
        assert as_bool("  true  ") is True
        assert as_bool("  false  ") is False
