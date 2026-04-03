"""Tests for image utility functions in deduplication module.

Tests image validation, metadata extraction, format comparison, directory
scanning, and quality ranking. PIL (Pillow) is mocked throughout.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level mock for PIL (optional dependency)
# ---------------------------------------------------------------------------
_mock_image_cls = MagicMock()

_pil_mod = ModuleType("PIL")
_pil_image_mod = ModuleType("PIL.Image")
_pil_image_mod.Image = _mock_image_cls  # type: ignore[attr-defined]
_pil_image_mod.open = _mock_image_cls.open  # type: ignore[attr-defined]

sys.modules.setdefault("PIL", _pil_mod)
sys.modules.setdefault("PIL.Image", _pil_image_mod)

from file_organizer.services.deduplication.image_utils import (  # noqa: E402
    FORMAT_QUALITY_RANK,
    SUPPORTED_FORMATS,
    ImageMetadata,
    compare_image_quality,
    filter_valid_images,
    find_images_in_directory,
    format_file_size,
    get_best_quality_image,
    get_format_quality_score,
    get_image_dimensions,
    get_image_format,
    get_image_info_string,
    get_image_metadata,
    group_images_by_format,
    is_supported_format,
    validate_image_file,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# ImageMetadata
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestImageMetadata:
    """Tests for ImageMetadata container."""

    def test_init_stores_attributes(self):
        meta = ImageMetadata(
            path=Path("img.png"),
            width=800,
            height=600,
            image_format="PNG",
            mode="RGB",
            size_bytes=102400,
        )
        assert meta.width == 800
        assert meta.height == 600
        assert meta.format == "PNG"
        assert meta.mode == "RGB"
        assert meta.size_bytes == 102400
        assert meta.resolution == 800 * 600

    def test_repr(self):
        meta = ImageMetadata(
            path=Path("img.png"),
            width=800,
            height=600,
            image_format="PNG",
            mode="RGB",
            size_bytes=102400,
        )
        rep = repr(meta)
        assert "img.png" in rep
        assert "800x600" in rep
        assert "PNG" in rep

    def test_to_dict(self):
        meta = ImageMetadata(
            path=Path("img.png"),
            width=800,
            height=600,
            image_format="PNG",
            mode="RGB",
            size_bytes=102400,
        )
        d = meta.to_dict()
        assert d["width"] == 800
        assert d["height"] == 600
        assert d["format"] == "PNG"
        assert d["resolution"] == 480000
        assert "path" in d


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConstants:
    """Tests for module-level constants."""

    def test_supported_formats_contains_common(self):
        for fmt in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"]:
            assert fmt in SUPPORTED_FORMATS

    def test_format_quality_rank(self):
        assert FORMAT_QUALITY_RANK[".png"] == 5
        assert FORMAT_QUALITY_RANK[".jpg"] == 2
        assert FORMAT_QUALITY_RANK[".gif"] == 1


# ---------------------------------------------------------------------------
# is_supported_format
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsSupportedFormat:
    """Tests for is_supported_format."""

    def test_supported(self):
        assert is_supported_format(Path("photo.jpg"))
        assert is_supported_format(Path("image.PNG"))

    def test_unsupported(self):
        assert not is_supported_format(Path("doc.pdf"))
        assert not is_supported_format(Path("song.mp3"))


# ---------------------------------------------------------------------------
# get_format_quality_score
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFormatQualityScore:
    """Tests for get_format_quality_score."""

    def test_known_formats(self):
        assert get_format_quality_score(Path("img.png")) == 5
        assert get_format_quality_score(Path("img.jpg")) == 2
        assert get_format_quality_score(Path("img.gif")) == 1

    def test_unknown_format(self):
        assert get_format_quality_score(Path("img.xyz")) == 0


# ---------------------------------------------------------------------------
# format_file_size
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatFileSize:
    """Tests for format_file_size."""

    def test_bytes(self):
        assert format_file_size(500) == "500.0 B"

    def test_kilobytes(self):
        result = format_file_size(1536)
        assert "KB" in result

    def test_megabytes(self):
        result = format_file_size(2 * 1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self):
        result = format_file_size(3 * 1024 * 1024 * 1024)
        assert "GB" in result

    def test_zero(self):
        assert format_file_size(0) == "0.0 B"


# ---------------------------------------------------------------------------
# get_image_metadata
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetImageMetadata:
    """Tests for get_image_metadata."""

    def test_nonexistent_file(self):
        result = get_image_metadata(Path("/nonexistent/img.png"))
        assert result is None

    def test_successful_extraction(self, tmp_path):
        p = tmp_path / "test.png"
        p.write_bytes(b"fake png data")

        mock_img = MagicMock()
        mock_img.size = (1920, 1080)
        mock_img.format = "PNG"
        mock_img.mode = "RGB"
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        with patch(
            "file_organizer.services.deduplication.image_utils.Image.open", return_value=mock_img
        ):
            result = get_image_metadata(p)

        assert result is not None
        assert result.width == 1920
        assert result.height == 1080
        assert result.format == "PNG"

    def test_os_error(self, tmp_path):
        p = tmp_path / "bad.png"
        p.write_bytes(b"bad")

        with patch(
            "file_organizer.services.deduplication.image_utils.Image.open",
            side_effect=OSError("corrupt"),
        ):
            result = get_image_metadata(p)

        assert result is None

    def test_generic_exception(self, tmp_path):
        p = tmp_path / "bad.png"
        p.write_bytes(b"bad")

        with patch(
            "file_organizer.services.deduplication.image_utils.Image.open",
            side_effect=RuntimeError("unknown"),
        ):
            result = get_image_metadata(p)

        assert result is None


# ---------------------------------------------------------------------------
# get_image_dimensions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetImageDimensions:
    """Tests for get_image_dimensions."""

    def test_success(self, tmp_path):
        p = tmp_path / "test.png"
        p.write_bytes(b"fake")

        mock_img = MagicMock()
        mock_img.size = (640, 480)
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        with patch(
            "file_organizer.services.deduplication.image_utils.Image.open", return_value=mock_img
        ):
            result = get_image_dimensions(p)

        assert result == (640, 480)

    def test_failure(self, tmp_path):
        p = tmp_path / "bad.png"
        p.write_bytes(b"bad")

        with patch(
            "file_organizer.services.deduplication.image_utils.Image.open",
            side_effect=OSError("fail"),
        ):
            result = get_image_dimensions(p)

        assert result is None


# ---------------------------------------------------------------------------
# get_image_format
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetImageFormat:
    """Tests for get_image_format."""

    def test_success(self, tmp_path):
        p = tmp_path / "test.png"
        p.write_bytes(b"fake")

        mock_img = MagicMock()
        mock_img.format = "PNG"
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        with patch(
            "file_organizer.services.deduplication.image_utils.Image.open", return_value=mock_img
        ):
            result = get_image_format(p)

        assert result == "PNG"

    def test_failure(self, tmp_path):
        p = tmp_path / "bad.png"
        p.write_bytes(b"bad")

        with patch(
            "file_organizer.services.deduplication.image_utils.Image.open",
            side_effect=OSError("fail"),
        ):
            result = get_image_format(p)

        assert result is None


# ---------------------------------------------------------------------------
# validate_image_file
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateImageFile:
    """Tests for validate_image_file."""

    def test_file_not_found(self):
        is_valid, msg = validate_image_file(Path("/nonexistent/img.png"))
        assert not is_valid
        assert "not found" in msg

    def test_not_a_file(self, tmp_path):
        is_valid, msg = validate_image_file(tmp_path)
        assert not is_valid
        assert "not a file" in msg

    def test_unsupported_format(self, tmp_path):
        p = tmp_path / "doc.pdf"
        p.write_bytes(b"fake pdf")
        is_valid, msg = validate_image_file(p)
        assert not is_valid
        assert "Unsupported" in msg

    def test_valid_image(self, tmp_path):
        p = tmp_path / "photo.jpg"
        p.write_bytes(b"fake jpg")

        mock_img_verify = MagicMock()
        mock_img_verify.__enter__ = MagicMock(return_value=mock_img_verify)
        mock_img_verify.__exit__ = MagicMock(return_value=False)

        mock_img_size = MagicMock()
        mock_img_size.size = (100, 100)
        mock_img_size.__enter__ = MagicMock(return_value=mock_img_size)
        mock_img_size.__exit__ = MagicMock(return_value=False)

        with patch(
            "file_organizer.services.deduplication.image_utils.Image.open",
            side_effect=[mock_img_verify, mock_img_size],
        ):
            is_valid, msg = validate_image_file(p)

        assert is_valid
        assert msg is None

    def test_corrupt_image(self, tmp_path):
        p = tmp_path / "corrupt.jpg"
        p.write_bytes(b"not an image")

        with patch(
            "file_organizer.services.deduplication.image_utils.Image.open",
            side_effect=OSError("corrupt"),
        ):
            is_valid, msg = validate_image_file(p)

        assert not is_valid
        assert "Cannot read" in msg


# ---------------------------------------------------------------------------
# filter_valid_images
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFilterValidImages:
    """Tests for filter_valid_images."""

    def test_filters_invalid(self, tmp_path):
        valid = tmp_path / "good.jpg"
        valid.write_bytes(b"fake")
        invalid = tmp_path / "bad.pdf"
        invalid.write_bytes(b"fake")

        with patch(
            "file_organizer.services.deduplication.image_utils.validate_image_file",
            side_effect=[(True, None), (False, "bad")],
        ):
            result = filter_valid_images([valid, invalid])

        assert len(result) == 1
        assert result[0] == valid


# ---------------------------------------------------------------------------
# find_images_in_directory
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindImagesInDirectory:
    """Tests for find_images_in_directory."""

    def test_nonexistent_dir(self):
        with pytest.raises(FileNotFoundError):
            find_images_in_directory(Path("/nonexistent"))

    def test_not_a_directory(self, tmp_path):
        p = tmp_path / "file.txt"
        p.write_text("hi")
        with pytest.raises(ValueError, match="not a directory"):
            find_images_in_directory(p)

    def test_finds_images(self, tmp_path):
        (tmp_path / "a.jpg").write_bytes(b"fake")
        (tmp_path / "b.png").write_bytes(b"fake")
        (tmp_path / "c.txt").write_text("text")

        result = find_images_in_directory(tmp_path, recursive=False)
        names = {p.name for p in result}
        assert "a.jpg" in names
        assert "b.png" in names
        assert "c.txt" not in names

    def test_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.png").write_bytes(b"fake")

        result = find_images_in_directory(tmp_path, recursive=True)
        names = {p.name for p in result}
        assert "deep.png" in names

    def test_non_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.png").write_bytes(b"fake")
        (tmp_path / "top.png").write_bytes(b"fake")

        result = find_images_in_directory(tmp_path, recursive=False)
        names = {p.name for p in result}
        assert "top.png" in names
        assert "deep.png" not in names

    def test_custom_extensions(self, tmp_path):
        (tmp_path / "a.jpg").write_bytes(b"fake")
        (tmp_path / "b.png").write_bytes(b"fake")

        result = find_images_in_directory(tmp_path, recursive=False, extensions=[".png"])
        names = {p.name for p in result}
        assert "b.png" in names
        assert "a.jpg" not in names

    def test_extensions_without_dot(self, tmp_path):
        (tmp_path / "a.jpg").write_bytes(b"fake")

        result = find_images_in_directory(tmp_path, recursive=False, extensions=["jpg"])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# group_images_by_format
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGroupImagesByFormat:
    """Tests for group_images_by_format."""

    def test_grouping(self):
        images = [Path("a.jpg"), Path("b.jpg"), Path("c.png")]
        groups = group_images_by_format(images)
        assert len(groups[".jpg"]) == 2
        assert len(groups[".png"]) == 1

    def test_empty_list(self):
        groups = group_images_by_format([])
        assert groups == {}


# ---------------------------------------------------------------------------
# compare_image_quality / get_best_quality_image
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCompareImageQuality:
    """Tests for compare_image_quality."""

    def test_both_none(self):
        with patch(
            "file_organizer.services.deduplication.image_utils.get_image_metadata",
            return_value=None,
        ):
            result = compare_image_quality(Path("a.jpg"), Path("b.jpg"))
        assert result == 0

    def test_first_none(self):
        meta = ImageMetadata(
            path=Path("b.jpg"),
            width=100,
            height=100,
            image_format="JPEG",
            mode="RGB",
            size_bytes=5000,
        )
        with patch(
            "file_organizer.services.deduplication.image_utils.get_image_metadata",
            side_effect=[None, meta],
        ):
            result = compare_image_quality(Path("a.jpg"), Path("b.jpg"))
        assert result == 1

    def test_second_none(self):
        meta = ImageMetadata(
            path=Path("a.jpg"),
            width=100,
            height=100,
            image_format="JPEG",
            mode="RGB",
            size_bytes=5000,
        )
        with patch(
            "file_organizer.services.deduplication.image_utils.get_image_metadata",
            side_effect=[meta, None],
        ):
            result = compare_image_quality(Path("a.jpg"), Path("b.jpg"))
        assert result == -1

    def test_higher_resolution_wins(self):
        meta1 = ImageMetadata(
            path=Path("a.png"),
            width=1920,
            height=1080,
            image_format="PNG",
            mode="RGB",
            size_bytes=5000,
        )
        meta2 = ImageMetadata(
            path=Path("b.png"),
            width=640,
            height=480,
            image_format="PNG",
            mode="RGB",
            size_bytes=5000,
        )
        with patch(
            "file_organizer.services.deduplication.image_utils.get_image_metadata",
            side_effect=[meta1, meta2],
        ):
            result = compare_image_quality(Path("a.png"), Path("b.png"))
        assert result == -1  # a is better

    def test_same_res_better_format_wins(self):
        meta1 = ImageMetadata(
            path=Path("a.png"),
            width=100,
            height=100,
            image_format="PNG",
            mode="RGB",
            size_bytes=5000,
        )
        meta2 = ImageMetadata(
            path=Path("b.jpg"),
            width=100,
            height=100,
            image_format="JPEG",
            mode="RGB",
            size_bytes=5000,
        )
        with patch(
            "file_organizer.services.deduplication.image_utils.get_image_metadata",
            side_effect=[meta1, meta2],
        ):
            result = compare_image_quality(Path("a.png"), Path("b.jpg"))
        assert result == -1  # PNG > JPEG

    def test_same_everything_larger_file_wins(self):
        meta1 = ImageMetadata(
            path=Path("a.png"),
            width=100,
            height=100,
            image_format="PNG",
            mode="RGB",
            size_bytes=10000,
        )
        meta2 = ImageMetadata(
            path=Path("b.png"),
            width=100,
            height=100,
            image_format="PNG",
            mode="RGB",
            size_bytes=5000,
        )
        with patch(
            "file_organizer.services.deduplication.image_utils.get_image_metadata",
            side_effect=[meta1, meta2],
        ):
            result = compare_image_quality(Path("a.png"), Path("b.png"))
        assert result == -1

    def test_truly_equal(self):
        meta = ImageMetadata(
            path=Path("a.png"),
            width=100,
            height=100,
            image_format="PNG",
            mode="RGB",
            size_bytes=5000,
        )
        with patch(
            "file_organizer.services.deduplication.image_utils.get_image_metadata",
            side_effect=[meta, meta],
        ):
            result = compare_image_quality(Path("a.png"), Path("b.png"))
        assert result == 0


@pytest.mark.unit
class TestGetBestQualityImage:
    """Tests for get_best_quality_image."""

    def test_empty_list(self):
        assert get_best_quality_image([]) is None

    def test_all_invalid(self):
        with patch(
            "file_organizer.services.deduplication.image_utils.filter_valid_images",
            return_value=[],
        ):
            assert get_best_quality_image([Path("a.jpg")]) is None


# ---------------------------------------------------------------------------
# get_image_info_string
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetImageInfoString:
    """Tests for get_image_info_string."""

    def test_with_valid_image(self):
        meta = ImageMetadata(
            path=Path("test.png"),
            width=1920,
            height=1080,
            image_format="PNG",
            mode="RGB",
            size_bytes=1024000,
        )
        with patch(
            "file_organizer.services.deduplication.image_utils.get_image_metadata",
            return_value=meta,
        ):
            result = get_image_info_string(Path("test.png"))
        assert "1920x1080" in result
        assert "PNG" in result

    def test_with_unreadable_image(self):
        with patch(
            "file_organizer.services.deduplication.image_utils.get_image_metadata",
            return_value=None,
        ):
            result = get_image_info_string(Path("bad.png"))
        assert "Cannot read" in result
