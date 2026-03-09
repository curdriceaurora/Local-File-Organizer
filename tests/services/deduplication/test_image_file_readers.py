"""Complementary image utility tests — issue #394.

Complements tests/services/deduplication/test_dedup_image_utils.py by:
- Testing extension/filesystem gate and mocked PIL calls using minimal image byte stubs
- Covering edge cases missing from the comprehensive deduplication test suite
- Providing @pytest.mark.smoke and @pytest.mark.ci coverage for the image reading pipeline

Tests target file_organizer.services.deduplication.image_utils and live here
to mirror the source module's location (services/deduplication/).

All tests mock PIL at the module level so they run without Pillow installed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level PIL mock (same pattern as test_dedup_image_utils.py)
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
    find_images_in_directory,
    get_best_quality_image,
    get_format_quality_score,
    is_supported_format,
    validate_image_file,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]

# ---------------------------------------------------------------------------
# Minimal image byte stubs (magic bytes only — no real image content)
# ---------------------------------------------------------------------------
_PNG_STUB = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_JPEG_STUB = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
_GIF_STUB = b"GIF89a" + b"\x00" * 10
_WEBP_STUB = b"RIFF" + b"\x00" * 4 + b"WEBP"

_IMAGE_OPEN_PATCH = "file_organizer.services.deduplication.image_utils.Image.open"


def _make_mock_img() -> MagicMock:
    """Return a context-manager-compatible PIL Image mock with minimal size."""
    mock_img = MagicMock()
    mock_img.size = (1, 1)
    mock_img.__enter__ = MagicMock(return_value=mock_img)
    mock_img.__exit__ = MagicMock(return_value=False)
    return mock_img


# ---------------------------------------------------------------------------
# TestSupportedFormatsCompleteness
# ---------------------------------------------------------------------------


class TestSupportedFormatsCompleteness:
    """Verify all expected image formats are registered as supported."""

    def test_all_expected_formats_present(self) -> None:
        expected = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"}
        assert SUPPORTED_FORMATS == expected

    def test_non_image_not_supported(self) -> None:
        for ext in [".pdf", ".docx", ".mp3", ".mp4", ".py", ".txt"]:
            assert not is_supported_format(Path(f"file{ext}")), f"{ext} should not be supported"

    @pytest.mark.smoke
    def test_tiff_variant_tif_supported(self) -> None:
        assert is_supported_format(Path("scan.tif"))
        assert is_supported_format(Path("scan.tiff"))

    def test_webp_supported(self) -> None:
        assert is_supported_format(Path("photo.webp"))

    def test_bmp_supported(self) -> None:
        assert is_supported_format(Path("bitmap.bmp"))

    def test_case_insensitive(self) -> None:
        assert is_supported_format(Path("PHOTO.JPG"))
        assert is_supported_format(Path("Image.PNG"))
        assert is_supported_format(Path("Banner.GIF"))


# ---------------------------------------------------------------------------
# TestMagicByteStubFiles
# ---------------------------------------------------------------------------


class TestMagicByteStubFiles:
    """Test image validation with minimal valid magic-byte stubs stored as files.

    validate_image_file() checks: exists → is_file → supported extension →
    PIL.open().verify() → PIL.open().size.  The first three checks are
    pure-Python (no PIL), so we can verify them with byte stubs.
    """

    def test_png_stub_passes_extension_check(self, tmp_path: Path) -> None:
        p = tmp_path / "image.png"
        p.write_bytes(_PNG_STUB)
        mock_img = _make_mock_img()
        with patch(_IMAGE_OPEN_PATCH, side_effect=[mock_img, mock_img]):
            is_valid, msg = validate_image_file(p)
        assert is_valid
        assert msg is None

    def test_jpeg_stub_passes_extension_check(self, tmp_path: Path) -> None:
        p = tmp_path / "photo.jpg"
        p.write_bytes(_JPEG_STUB)
        mock_img = _make_mock_img()
        with patch(_IMAGE_OPEN_PATCH, side_effect=[mock_img, mock_img]):
            is_valid, msg = validate_image_file(p)
        assert is_valid
        assert msg is None

    def test_gif_stub_passes_extension_check(self, tmp_path: Path) -> None:
        p = tmp_path / "anim.gif"
        p.write_bytes(_GIF_STUB)
        mock_img = _make_mock_img()
        with patch(_IMAGE_OPEN_PATCH, side_effect=[mock_img, mock_img]):
            is_valid, msg = validate_image_file(p)
        assert is_valid
        assert msg is None

    def test_webp_stub_passes_extension_check(self, tmp_path: Path) -> None:
        p = tmp_path / "photo.webp"
        p.write_bytes(_WEBP_STUB)
        mock_img = _make_mock_img()
        with patch(_IMAGE_OPEN_PATCH, side_effect=[mock_img, mock_img]):
            is_valid, msg = validate_image_file(p)
        assert is_valid
        assert msg is None

    def test_non_image_extension_rejected_before_pil(self, tmp_path: Path) -> None:
        """Extension check runs before PIL; .pdf should be rejected without PIL call."""
        p = tmp_path / "document.pdf"
        p.write_bytes(_PNG_STUB)  # correct image bytes but wrong extension

        with patch("file_organizer.services.deduplication.image_utils.Image.open") as mock_open:
            is_valid, msg = validate_image_file(p)

        assert not is_valid
        assert "Unsupported" in msg
        mock_open.assert_not_called()  # extension gate fires first


# ---------------------------------------------------------------------------
# TestQualityScoreRanking
# ---------------------------------------------------------------------------


class TestQualityScoreRanking:
    """Test that quality scores form a total ordering."""

    def test_lossless_beats_lossy(self) -> None:
        """PNG (5) must score higher than JPEG (2)."""
        png_score = get_format_quality_score(Path("a.png"))
        jpg_score = get_format_quality_score(Path("b.jpg"))
        assert png_score > jpg_score

    def test_tiff_equals_png(self) -> None:
        assert get_format_quality_score(Path("a.tiff")) == get_format_quality_score(Path("b.png"))

    def test_gif_is_lowest(self) -> None:
        gif_score = get_format_quality_score(Path("a.gif"))
        for ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"]:
            assert get_format_quality_score(Path(f"x{ext}")) >= gif_score

    def test_full_ranking_is_total_order(self) -> None:
        """Pin every rank so mid-table regressions (e.g. bmp < webp) are caught."""
        scores = {ext: get_format_quality_score(Path(f"x{ext}")) for ext in FORMAT_QUALITY_RANK}
        # Verify the documented ranking: PNG/TIFF (5) > BMP (4) > WEBP (3) > JPEG (2) > GIF (1)
        assert scores[".png"] == scores[".tiff"] == scores[".tif"]
        assert scores[".png"] > scores[".bmp"]
        assert scores[".bmp"] > scores[".webp"]
        assert scores[".webp"] > scores[".jpg"] == scores[".jpeg"]
        assert scores[".jpg"] > scores[".gif"]


# ---------------------------------------------------------------------------
# TestGetBestQualityImageEdgeCases
# ---------------------------------------------------------------------------


class TestGetBestQualityImageEdgeCases:
    """Edge cases for get_best_quality_image not covered in dedup test suite."""

    def test_single_valid_image_returned_as_best(self, tmp_path: Path) -> None:
        """A list with one valid image must return that image."""
        p = tmp_path / "only.png"
        p.write_bytes(_PNG_STUB)

        meta = ImageMetadata(
            path=p,
            width=800,
            height=600,
            image_format="PNG",
            mode="RGB",
            size_bytes=len(_PNG_STUB),
        )

        with (
            patch(
                "file_organizer.services.deduplication.image_utils.filter_valid_images",
                return_value=[p],
            ),
            patch(
                "file_organizer.services.deduplication.image_utils.get_image_metadata",
                return_value=meta,
            ),
        ):
            result = get_best_quality_image([p])

        assert result == p

    def test_png_beats_jpeg_same_resolution(self, tmp_path: Path) -> None:
        """When resolution is equal, PNG quality score should win over JPEG."""
        png = tmp_path / "photo.png"
        jpg = tmp_path / "photo.jpg"
        png.write_bytes(_PNG_STUB)
        jpg.write_bytes(_JPEG_STUB)

        meta_png = ImageMetadata(
            path=png,
            width=100,
            height=100,
            image_format="PNG",
            mode="RGB",
            size_bytes=1000,
        )
        meta_jpg = ImageMetadata(
            path=jpg,
            width=100,
            height=100,
            image_format="JPEG",
            mode="RGB",
            size_bytes=1000,
        )

        with (
            patch(
                "file_organizer.services.deduplication.image_utils.filter_valid_images",
                return_value=[png, jpg],
            ),
            patch(
                "file_organizer.services.deduplication.image_utils.get_image_metadata",
                side_effect=[meta_png, meta_jpg],
            ),
        ):
            result = get_best_quality_image([png, jpg])

        assert result == png


# ---------------------------------------------------------------------------
# TestCompareImageQualityAdditional
# ---------------------------------------------------------------------------


class TestCompareImageQualityAdditional:
    """Additional compare_image_quality cases."""

    def test_both_zero_resolution_falls_back_to_format(self) -> None:
        """Both images have 0×0 resolution; format score determines winner."""
        meta_png = ImageMetadata(
            path=Path("a.png"),
            width=0,
            height=0,
            image_format="PNG",
            mode="RGB",
            size_bytes=500,
        )
        meta_jpg = ImageMetadata(
            path=Path("b.jpg"),
            width=0,
            height=0,
            image_format="JPEG",
            mode="RGB",
            size_bytes=500,
        )
        with patch(
            "file_organizer.services.deduplication.image_utils.get_image_metadata",
            side_effect=[meta_png, meta_jpg],
        ):
            result = compare_image_quality(Path("a.png"), Path("b.jpg"))
        # PNG > JPEG
        assert result == -1


# ---------------------------------------------------------------------------
# TestFindImagesAdditional
# ---------------------------------------------------------------------------


class TestFindImagesAdditional:
    """Additional find_images_in_directory cases."""

    @pytest.mark.smoke
    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        result = find_images_in_directory(tmp_path)
        assert result == []

    def test_mixed_case_extensions_found(self, tmp_path: Path) -> None:
        (tmp_path / "PHOTO.JPG").write_bytes(_JPEG_STUB)
        (tmp_path / "banner.PNG").write_bytes(_PNG_STUB)

        result = find_images_in_directory(tmp_path, recursive=False)
        names = {p.name for p in result}
        assert "PHOTO.JPG" in names
        assert "banner.PNG" in names

    def test_hidden_files_included(self, tmp_path: Path) -> None:
        """Hidden image files (dot-prefix) should be found like any other file."""
        (tmp_path / ".hidden.jpg").write_bytes(_JPEG_STUB)

        result = find_images_in_directory(tmp_path, recursive=False)
        names = {p.name for p in result}
        assert ".hidden.jpg" in names
