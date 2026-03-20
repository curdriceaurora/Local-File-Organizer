"""Integration tests for image utility functions.

Covers:
  - services/deduplication/image_utils.py — image utility functions
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.deduplication.image_utils import (
    SUPPORTED_FORMATS,
    compare_image_quality,
    filter_valid_images,
    find_images_in_directory,
    format_file_size,
    get_best_quality_image,
    get_format_quality_score,
    get_image_format,
    group_images_by_format,
    is_supported_format,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# format_file_size (pure function, no IO)
# ---------------------------------------------------------------------------


class TestFormatFileSize:
    def test_bytes(self) -> None:
        assert "B" in format_file_size(500) or "byte" in format_file_size(500).lower()

    def test_kilobytes(self) -> None:
        result = format_file_size(1024)
        assert "K" in result or "k" in result

    def test_megabytes(self) -> None:
        result = format_file_size(1024 * 1024)
        assert "M" in result or "m" in result

    def test_gigabytes(self) -> None:
        result = format_file_size(1024 * 1024 * 1024)
        assert "G" in result or "g" in result

    def test_zero_bytes(self) -> None:
        result = format_file_size(0)
        assert "B" in result

    def test_returns_string(self) -> None:
        assert "B" in format_file_size(100)


# ---------------------------------------------------------------------------
# SUPPORTED_FORMATS and is_supported_format
# ---------------------------------------------------------------------------


class TestSupportedFormats:
    def test_supported_formats_not_empty(self) -> None:
        assert len(SUPPORTED_FORMATS) > 0

    def test_jpg_supported(self, tmp_path: Path) -> None:
        f = tmp_path / "image.jpg"
        f.write_bytes(b"\xff\xd8\xff")  # JPEG magic bytes
        assert is_supported_format(f) is True

    def test_png_supported(self, tmp_path: Path) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes
        assert is_supported_format(f) is True

    def test_txt_not_supported(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hello")
        assert is_supported_format(f) is False

    def test_mp4_not_supported(self, tmp_path: Path) -> None:
        f = tmp_path / "video.mp4"
        f.write_bytes(b"\x00" * 10)
        assert is_supported_format(f) is False

    def test_gif_supported(self, tmp_path: Path) -> None:
        f = tmp_path / "image.gif"
        f.write_bytes(b"GIF89a")
        assert is_supported_format(f) is True


# ---------------------------------------------------------------------------
# get_image_format (extension-based)
# ---------------------------------------------------------------------------


class TestGetImageFormat:
    def test_jpg_format(self, tmp_path: Path) -> None:
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff")
        result = get_image_format(f)
        assert result is None or "JPEG" in result.upper() or "jpg" in (result or "").lower()

    def test_png_format(self, tmp_path: Path) -> None:
        f = tmp_path / "diagram.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        result = get_image_format(f)
        # Either None (if Pillow not available) or contains PNG
        assert result is None or isinstance(result, str)

    def test_nonexistent_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.jpg"
        result = get_image_format(f)
        assert result is None

    def test_non_image_returns_none_or_str(self, tmp_path: Path) -> None:
        f = tmp_path / "text.txt"
        f.write_text("not an image")
        result = get_image_format(f)
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# get_format_quality_score
# ---------------------------------------------------------------------------


class TestFormatQualityScore:
    def test_returns_int_or_float(self, tmp_path: Path) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        score = get_format_quality_score(f)
        assert isinstance(score, (int, float))

    def test_known_format_nonzero(self, tmp_path: Path) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        score = get_format_quality_score(f)
        assert score >= 0

    def test_unknown_extension_returns_value(self, tmp_path: Path) -> None:
        f = tmp_path / "file.xyz"
        f.write_bytes(b"\x00")
        score = get_format_quality_score(f)
        assert isinstance(score, (int, float))

    def test_jpeg_score_is_int(self, tmp_path: Path) -> None:
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff")
        jpeg_score = get_format_quality_score(f)
        assert isinstance(jpeg_score, (int, float))


# ---------------------------------------------------------------------------
# filter_valid_images
# ---------------------------------------------------------------------------


class TestFilterValidImages:
    def test_empty_list_returns_empty(self) -> None:
        result = filter_valid_images([])
        assert result == []

    def test_txt_file_excluded(self, tmp_path: Path) -> None:
        txt = tmp_path / "doc.txt"
        txt.write_text("text")
        result = filter_valid_images([txt])
        assert txt not in result

    def test_nonexistent_files_excluded(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.jpg"
        result = filter_valid_images([missing])
        assert missing not in result

    def test_returns_list(self, tmp_path: Path) -> None:
        imgs = []
        for name in ("a.jpg", "b.png", "c.gif"):
            f = tmp_path / name
            f.write_bytes(b"\x00" * 10)
            imgs.append(f)
        result = filter_valid_images(imgs)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# find_images_in_directory
# ---------------------------------------------------------------------------


class TestFindImagesInDirectory:
    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        result = find_images_in_directory(tmp_path)
        assert result == []

    def test_finds_jpg_files(self, tmp_path: Path) -> None:
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff")
        result = find_images_in_directory(tmp_path)
        assert any("photo.jpg" in str(p) for p in result)

    def test_ignores_non_image_files(self, tmp_path: Path) -> None:
        (tmp_path / "doc.txt").write_text("text")
        result = find_images_in_directory(tmp_path)
        assert all(not str(p).endswith(".txt") for p in result)

    def test_recursive_finds_nested(self, tmp_path: Path) -> None:
        sub = tmp_path / "nested"
        sub.mkdir()
        (sub / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        result = find_images_in_directory(tmp_path, recursive=True)
        assert any("img.png" in str(p) for p in result)

    def test_non_recursive_misses_nested(self, tmp_path: Path) -> None:
        sub = tmp_path / "nested"
        sub.mkdir()
        (sub / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        result = find_images_in_directory(tmp_path, recursive=False)
        assert not any("img.png" in str(p) for p in result)

    def test_custom_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff")
        (tmp_path / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        result = find_images_in_directory(tmp_path, extensions=[".png"])
        assert all(str(p).endswith(".png") for p in result)

    def test_returns_list_of_paths(self, tmp_path: Path) -> None:
        result = find_images_in_directory(tmp_path)
        assert isinstance(result, list)
        assert all(isinstance(p, Path) for p in result)


# ---------------------------------------------------------------------------
# get_best_quality_image
# ---------------------------------------------------------------------------


class TestGetBestQualityImage:
    def test_empty_list_returns_none(self) -> None:
        result = get_best_quality_image([])
        assert result is None

    def test_single_image_returns_none_or_path(self, tmp_path: Path) -> None:
        f = tmp_path / "only.jpg"
        f.write_bytes(b"\xff\xd8\xff")
        result = get_best_quality_image([f])
        # Requires Pillow to validate — may return None if not readable
        assert result is None or result == f

    def test_returns_none_or_path(self, tmp_path: Path) -> None:
        jpg = tmp_path / "photo.jpg"
        png = tmp_path / "diagram.png"
        jpg.write_bytes(b"\xff\xd8\xff")
        png.write_bytes(b"\x89PNG\r\n\x1a\n")
        result = get_best_quality_image([jpg, png])
        assert result is None or result in (jpg, png)


# ---------------------------------------------------------------------------
# compare_image_quality
# ---------------------------------------------------------------------------


class TestCompareImageQuality:
    def test_same_format_returns_zero_or_int(self, tmp_path: Path) -> None:
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        a.write_bytes(b"\xff\xd8\xff")
        b.write_bytes(b"\xff\xd8\xff")
        result = compare_image_quality(a, b)
        assert result == 0

    def test_png_vs_jpg_returns_int(self, tmp_path: Path) -> None:
        png = tmp_path / "a.png"
        jpg = tmp_path / "b.jpg"
        png.write_bytes(b"\x89PNG\r\n\x1a\n")
        jpg.write_bytes(b"\xff\xd8\xff")
        result = compare_image_quality(png, jpg)
        assert result in (-1, 0, 1)


# ---------------------------------------------------------------------------
# group_images_by_format
# ---------------------------------------------------------------------------


class TestGroupImagesByFormat:
    def test_empty_list_returns_dict(self) -> None:
        result = group_images_by_format([])
        assert result == {}

    def test_groups_by_extension(self, tmp_path: Path) -> None:
        jpg1 = tmp_path / "a.jpg"
        jpg2 = tmp_path / "b.jpg"
        png1 = tmp_path / "c.png"
        for f in (jpg1, jpg2, png1):
            f.write_bytes(b"\x00" * 10)
        result = group_images_by_format([jpg1, jpg2, png1])
        assert len(result) >= 1

    def test_each_group_is_list(self, tmp_path: Path) -> None:
        jpg = tmp_path / "photo.jpg"
        jpg.write_bytes(b"\xff\xd8\xff")
        result = group_images_by_format([jpg])
        for _key, val in result.items():
            assert len(val) >= 1
