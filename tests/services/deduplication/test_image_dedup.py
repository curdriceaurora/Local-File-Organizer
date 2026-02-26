"""Tests for ImageDeduplicator class.

Tests perceptual hashing, similarity computation, duplicate finding,
clustering, batch hashing, image validation, and file discovery.

The ``imagededup`` library is an optional dependency that may not be
installed in every environment.  We mock it (and PIL) at the *module*
level so the test suite works regardless.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level mocks for optional dependencies (imagededup, PIL)
# ---------------------------------------------------------------------------
# imagededup may not be installed; we need to inject fake modules *before*
# importing the module under test so that ``from imagededup.methods import …``
# succeeds.

_mock_phash_cls = MagicMock()
_mock_dhash_cls = MagicMock()
_mock_ahash_cls = MagicMock()

_imagededup_mod = ModuleType("imagededup")
_imagededup_methods_mod = ModuleType("imagededup.methods")
_imagededup_methods_mod.PHash = _mock_phash_cls  # type: ignore[attr-defined]
_imagededup_methods_mod.DHash = _mock_dhash_cls  # type: ignore[attr-defined]
_imagededup_methods_mod.AHash = _mock_ahash_cls  # type: ignore[attr-defined]

sys.modules.setdefault("imagededup", _imagededup_mod)
sys.modules.setdefault("imagededup.methods", _imagededup_methods_mod)

# Now import the module under test – the mocked modules will satisfy the
# ``from imagededup.methods import …`` statement.
from file_organizer.services.deduplication.image_dedup import ImageDeduplicator  # noqa: E402


# ---------------------------------------------------------------------------
# Helper – build a deduplicator with a controllable hasher mock
# ---------------------------------------------------------------------------
def _make_dedup(hash_method: str = "phash", threshold: int = 10) -> ImageDeduplicator:
    """Create an ImageDeduplicator and replace its hasher with a fresh mock."""
    dedup = ImageDeduplicator(hash_method=hash_method, threshold=threshold)
    dedup.hasher = MagicMock()
    return dedup


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------
class TestImageDeduplicatorInit:
    """Test ImageDeduplicator initialization and validation."""

    def test_default_init(self):
        """Test default phash method and threshold=10."""
        dedup = ImageDeduplicator()
        assert dedup.hash_method == "phash"
        assert dedup.threshold == 10

    def test_init_phash(self):
        """Test explicit phash initialization."""
        dedup = ImageDeduplicator(hash_method="phash", threshold=5)
        assert dedup.hash_method == "phash"
        assert dedup.threshold == 5

    def test_init_dhash(self):
        """Test dhash initialization."""
        dedup = ImageDeduplicator(hash_method="dhash", threshold=15)
        assert dedup.hash_method == "dhash"
        assert dedup.threshold == 15

    def test_init_ahash(self):
        """Test ahash initialization."""
        dedup = ImageDeduplicator(hash_method="ahash", threshold=0)
        assert dedup.hash_method == "ahash"
        assert dedup.threshold == 0

    def test_invalid_hash_method(self):
        """Test that unsupported hash method raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported hash method"):
            ImageDeduplicator(hash_method="md5")

    def test_threshold_below_zero(self):
        """Test that negative threshold raises ValueError."""
        with pytest.raises(ValueError, match="Threshold must be between 0 and 64"):
            ImageDeduplicator(threshold=-1)

    def test_threshold_above_64(self):
        """Test that threshold above 64 raises ValueError."""
        with pytest.raises(ValueError, match="Threshold must be between 0 and 64"):
            ImageDeduplicator(threshold=65)

    def test_threshold_boundary_zero(self):
        """Test threshold at lower boundary (0)."""
        dedup = ImageDeduplicator(threshold=0)
        assert dedup.threshold == 0

    def test_threshold_boundary_64(self):
        """Test threshold at upper boundary (64)."""
        dedup = ImageDeduplicator(threshold=64)
        assert dedup.threshold == 64


# ---------------------------------------------------------------------------
# get_image_hash
# ---------------------------------------------------------------------------
class TestGetImageHash:
    """Test single-image hash computation."""

    def test_hash_valid_image(self, tmp_path: Path):
        """Test successful hash of a valid image file."""
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-data")

        dedup = _make_dedup()
        dedup.hasher.encode_image.return_value = "abcdef1234567890"

        result = dedup.get_image_hash(img)
        assert result == "abcdef1234567890"
        dedup.hasher.encode_image.assert_called_once_with(str(img))

    def test_hash_nonexistent_file(self, tmp_path: Path):
        """Test that missing file returns None."""
        dedup = _make_dedup()
        result = dedup.get_image_hash(tmp_path / "missing.jpg")
        assert result is None

    def test_hash_directory_path(self, tmp_path: Path):
        """Test that directory path returns None."""
        dedup = _make_dedup()
        result = dedup.get_image_hash(tmp_path)
        assert result is None

    def test_hash_unsupported_format(self, tmp_path: Path):
        """Test that unsupported format returns None."""
        txt = tmp_path / "readme.txt"
        txt.write_text("hello")
        dedup = _make_dedup()
        result = dedup.get_image_hash(txt)
        assert result is None

    def test_hash_os_error(self, tmp_path: Path):
        """Test that OSError during encoding returns None."""
        img = tmp_path / "corrupt.png"
        img.write_bytes(b"\x89PNGcorrupt")

        dedup = _make_dedup()
        dedup.hasher.encode_image.side_effect = OSError("bad file")
        result = dedup.get_image_hash(img)
        assert result is None

    def test_hash_unexpected_exception(self, tmp_path: Path):
        """Test that unexpected exception during encoding returns None."""
        img = tmp_path / "weird.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0junk")

        dedup = _make_dedup()
        dedup.hasher.encode_image.side_effect = RuntimeError("kaboom")
        result = dedup.get_image_hash(img)
        assert result is None

    def test_hash_supported_formats(self, tmp_path: Path):
        """Test that each supported extension is accepted."""
        dedup = _make_dedup()
        dedup.hasher.encode_image.return_value = "aabbccdd"

        for ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"):
            img = tmp_path / f"image{ext}"
            img.write_bytes(b"\x00" * 10)
            result = dedup.get_image_hash(img)
            assert result == "aabbccdd", f"Failed for extension {ext}"


# ---------------------------------------------------------------------------
# compute_hamming_distance
# ---------------------------------------------------------------------------
class TestComputeHammingDistance:
    """Test Hamming distance calculation between hashes."""

    def test_identical_hashes(self):
        """Test distance of zero for identical hashes."""
        dedup = _make_dedup()
        assert dedup.compute_hamming_distance("abcd", "abcd") == 0

    def test_completely_different(self):
        """Test maximum distance for 16-hex-char (64-bit) hashes."""
        dedup = _make_dedup()
        h1 = "0000000000000000"
        h2 = "ffffffffffffffff"
        assert dedup.compute_hamming_distance(h1, h2) == 64

    def test_single_bit_difference(self):
        """Test distance of 1 for one-bit difference."""
        dedup = _make_dedup()
        assert dedup.compute_hamming_distance("0", "1") == 1

    def test_known_distance(self):
        """Test known Hamming distance value."""
        dedup = _make_dedup()
        # 0x0f = 0b00001111, 0x00 = 0b00000000 -> 4 bits differ
        assert dedup.compute_hamming_distance("0f", "00") == 4

    def test_invalid_hex_hash1(self):
        """Test that non-hex first hash raises ValueError."""
        dedup = _make_dedup()
        with pytest.raises(ValueError, match="Invalid hash format"):
            dedup.compute_hamming_distance("xyz", "abc")

    def test_invalid_hex_hash2(self):
        """Test that non-hex second hash raises ValueError."""
        dedup = _make_dedup()
        with pytest.raises(ValueError, match="Invalid hash format"):
            dedup.compute_hamming_distance("abc", "not_hex!")

    def test_empty_strings(self):
        """Test that empty strings raise ValueError."""
        dedup = _make_dedup()
        with pytest.raises(ValueError, match="Invalid hash format"):
            dedup.compute_hamming_distance("", "")


# ---------------------------------------------------------------------------
# compute_similarity
# ---------------------------------------------------------------------------
class TestComputeSimilarity:
    """Test image similarity scoring."""

    def test_identical_images(self, tmp_path: Path):
        """Test perfect similarity for images with identical hashes."""
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"\xff\xd8data1")
        img2.write_bytes(b"\xff\xd8data2")

        dedup = _make_dedup()
        dedup.hasher.encode_image.return_value = "abcdef1234567890"

        result = dedup.compute_similarity(img1, img2)
        assert result == 1.0

    def test_completely_different(self, tmp_path: Path):
        """Test zero similarity for maximally different hashes."""
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"\xff\xd8data1")
        img2.write_bytes(b"\xff\xd8data2")

        dedup = _make_dedup()
        dedup.hasher.encode_image.side_effect = [
            "0000000000000000",
            "ffffffffffffffff",
        ]

        result = dedup.compute_similarity(img1, img2)
        assert result == 0.0

    def test_partial_similarity(self, tmp_path: Path):
        """Test partial similarity with known distance."""
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"\xff\xd8data1")
        img2.write_bytes(b"\xff\xd8data2")

        dedup = _make_dedup()
        # 0x000000000000000f vs 0x0000000000000000 -> 4 bits differ
        dedup.hasher.encode_image.side_effect = [
            "0000000000000000",
            "000000000000000f",
        ]

        result = dedup.compute_similarity(img1, img2)
        assert result == pytest.approx(1.0 - 4 / 64.0)

    def test_first_image_fails(self, tmp_path: Path):
        """Test None returned when first image can't be hashed."""
        img1 = tmp_path / "missing.jpg"  # does not exist
        img2 = tmp_path / "b.jpg"
        img2.write_bytes(b"\xff\xd8data2")

        dedup = _make_dedup()
        result = dedup.compute_similarity(img1, img2)
        assert result is None

    def test_second_image_fails(self, tmp_path: Path):
        """Test None returned when second image can't be hashed."""
        img1 = tmp_path / "a.jpg"
        img1.write_bytes(b"\xff\xd8data1")
        img2 = tmp_path / "missing.jpg"

        dedup = _make_dedup()
        result = dedup.compute_similarity(img1, img2)
        assert result is None


# ---------------------------------------------------------------------------
# find_duplicates
# ---------------------------------------------------------------------------
class TestFindDuplicates:
    """Test directory-level duplicate detection."""

    def test_nonexistent_directory(self):
        """Test FileNotFoundError for missing directory."""
        dedup = _make_dedup()
        with pytest.raises(FileNotFoundError, match="Directory not found"):
            dedup.find_duplicates(Path("/no/such/dir"))

    def test_not_a_directory(self, tmp_path: Path):
        """Test ValueError for path that is a file, not a directory."""
        f = tmp_path / "file.txt"
        f.write_text("x")
        dedup = _make_dedup()
        with pytest.raises(ValueError, match="Path is not a directory"):
            dedup.find_duplicates(f)

    def test_empty_directory(self, tmp_path: Path):
        """Test empty result for directory with no images."""
        dedup = _make_dedup()
        result = dedup.find_duplicates(tmp_path)
        assert result == {}

    def test_no_duplicates(self, tmp_path: Path):
        """Test empty result when all images are unique."""
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.png"
        img1.write_bytes(b"\xff\xd8data1")
        img2.write_bytes(b"\x89PNGdata2")

        dedup = _make_dedup()
        dedup.hasher.encode_image.side_effect = ["hash1", "hash2"]
        dedup.hasher.find_duplicates.return_value = {
            str(img1): [],
            str(img2): [],
        }

        result = dedup.find_duplicates(tmp_path)
        assert result == {}

    def test_duplicates_found(self, tmp_path: Path):
        """Test grouping when duplicates exist."""
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img3 = tmp_path / "c.png"
        for img in (img1, img2, img3):
            img.write_bytes(b"\xff\xd8fakeimage")

        dedup = _make_dedup()
        dedup.hasher.encode_image.side_effect = ["hash_a", "hash_b", "hash_c"]
        dedup.hasher.find_duplicates.return_value = {
            str(img1): [str(img2)],
            str(img2): [str(img1)],
            str(img3): [],
        }

        result = dedup.find_duplicates(tmp_path)
        assert len(result) == 1
        group = list(result.values())[0]
        assert img1 in group
        assert img2 in group

    def test_progress_callback(self, tmp_path: Path):
        """Test that progress callback is invoked for each image."""
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8data")

        dedup = _make_dedup()
        dedup.hasher.encode_image.return_value = "somehash"
        dedup.hasher.find_duplicates.return_value = {str(img): []}

        callback = MagicMock()
        dedup.find_duplicates(tmp_path, progress_callback=callback)
        callback.assert_called_once_with(1, 1)

    def test_recursive_scanning(self, tmp_path: Path):
        """Test recursive=True finds images in subdirectories."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        img = subdir / "nested.jpg"
        img.write_bytes(b"\xff\xd8data")

        dedup = _make_dedup()
        dedup.hasher.encode_image.return_value = "nested_hash"
        dedup.hasher.find_duplicates.return_value = {str(img): []}

        dedup.find_duplicates(tmp_path, recursive=True)
        dedup.hasher.encode_image.assert_called_once()

    def test_non_recursive_scanning(self, tmp_path: Path):
        """Test recursive=False does NOT find images in subdirectories."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "nested.jpg").write_bytes(b"\xff\xd8data")
        root_img = tmp_path / "root.jpg"
        root_img.write_bytes(b"\xff\xd8data")

        dedup = _make_dedup()
        dedup.hasher.encode_image.return_value = "root_hash"
        dedup.hasher.find_duplicates.return_value = {str(root_img): []}

        dedup.find_duplicates(tmp_path, recursive=False)
        dedup.hasher.encode_image.assert_called_once_with(str(root_img))

    def test_skips_unhashable_images(self, tmp_path: Path):
        """Test that images failing to hash are excluded."""
        good = tmp_path / "good.jpg"
        bad = tmp_path / "bad.jpg"
        good.write_bytes(b"\xff\xd8good")
        bad.write_bytes(b"\xff\xd8bad")

        dedup = _make_dedup()

        # encode_image should return hash for good, None for bad (order-independent)
        def encode_image_side_effect(path: str) -> str | None:
            if path == str(good):
                return "good_hash"
            elif path == str(bad):
                return None
            return None

        dedup.hasher.encode_image.side_effect = encode_image_side_effect
        dedup.hasher.find_duplicates.return_value = {str(good): []}

        dedup.find_duplicates(tmp_path)
        call_kwargs = dedup.hasher.find_duplicates.call_args
        encoding_map = call_kwargs.kwargs.get(
            "encoding_map", call_kwargs[1].get("encoding_map")
        )
        assert str(good) in encoding_map
        assert str(bad) not in encoding_map


# ---------------------------------------------------------------------------
# cluster_by_similarity
# ---------------------------------------------------------------------------
class TestClusterBySimilarity:
    """Test image clustering."""

    def test_empty_list(self):
        """Test empty input returns empty clusters."""
        dedup = _make_dedup()
        assert dedup.cluster_by_similarity([]) == []

    def test_all_hashes_fail(self, tmp_path: Path):
        """Test empty clusters when no image can be hashed."""
        img = tmp_path / "bad.jpg"
        img.write_bytes(b"\xff\xd8corrupt")

        dedup = _make_dedup()
        dedup.hasher.encode_image.return_value = None

        result = dedup.cluster_by_similarity([img])
        assert result == []

    def test_single_image_no_cluster(self, tmp_path: Path):
        """Test that a single image does not form a cluster."""
        img = tmp_path / "solo.jpg"
        img.write_bytes(b"\xff\xd8solo")

        dedup = _make_dedup()
        dedup.hasher.encode_image.return_value = "0000000000000000"

        result = dedup.cluster_by_similarity([img])
        assert result == []

    def test_two_identical_images(self, tmp_path: Path):
        """Test cluster of two identical images."""
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"\xff\xd8data")
        img2.write_bytes(b"\xff\xd8data")

        dedup = _make_dedup(threshold=10)
        dedup.hasher.encode_image.return_value = "abcdef1234567890"

        result = dedup.cluster_by_similarity([img1, img2])
        assert len(result) == 1
        assert img1 in result[0]
        assert img2 in result[0]

    def test_two_different_images(self, tmp_path: Path):
        """Test no clusters for very different images."""
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"\xff\xd8data1")
        img2.write_bytes(b"\xff\xd8data2")

        dedup = _make_dedup(threshold=0)
        dedup.hasher.encode_image.side_effect = [
            "0000000000000000",
            "ffffffffffffffff",
        ]

        result = dedup.cluster_by_similarity([img1, img2])
        assert result == []

    def test_progress_callback(self, tmp_path: Path):
        """Test progress callback is called during clustering."""
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"\xff\xd8d1")
        img2.write_bytes(b"\xff\xd8d2")

        dedup = _make_dedup()
        dedup.hasher.encode_image.return_value = "aabb"

        callback = MagicMock()
        dedup.cluster_by_similarity([img1, img2], progress_callback=callback)
        assert callback.call_count == 2
        callback.assert_any_call(1, 2)
        callback.assert_any_call(2, 2)

    def test_multiple_clusters(self, tmp_path: Path):
        """Test forming multiple distinct clusters."""
        imgs = []
        for name in ("a.jpg", "b.jpg", "c.jpg", "d.jpg"):
            p = tmp_path / name
            p.write_bytes(b"\xff\xd8data")
            imgs.append(p)

        dedup = _make_dedup(threshold=5)
        # a, b share hash "0...0"; c, d share hash "f...f"; distance 64 apart
        dedup.hasher.encode_image.side_effect = [
            "0000000000000000",
            "0000000000000000",
            "ffffffffffffffff",
            "ffffffffffffffff",
        ]

        result = dedup.cluster_by_similarity(imgs)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# batch_compute_hashes
# ---------------------------------------------------------------------------
class TestBatchComputeHashes:
    """Test batch hash computation."""

    def test_empty_list(self):
        """Test empty input returns empty dict."""
        dedup = _make_dedup()
        assert dedup.batch_compute_hashes([]) == {}

    def test_all_succeed(self, tmp_path: Path):
        """Test all images hashed successfully."""
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.png"
        img1.write_bytes(b"\xff\xd8d1")
        img2.write_bytes(b"\x89PNGd2")

        dedup = _make_dedup()
        dedup.hasher.encode_image.side_effect = ["hash_a", "hash_b"]

        result = dedup.batch_compute_hashes([img1, img2])
        assert result == {img1: "hash_a", img2: "hash_b"}

    def test_partial_failure(self, tmp_path: Path):
        """Test that failed images are excluded from results."""
        good = tmp_path / "good.jpg"
        bad = tmp_path / "bad.jpg"
        good.write_bytes(b"\xff\xd8good")
        bad.write_bytes(b"\xff\xd8bad")

        dedup = _make_dedup()
        dedup.hasher.encode_image.side_effect = ["good_hash", None]

        result = dedup.batch_compute_hashes([good, bad])
        assert result == {good: "good_hash"}

    def test_progress_callback(self, tmp_path: Path):
        """Test progress callback invoked for each image."""
        imgs = []
        for i in range(3):
            p = tmp_path / f"img{i}.jpg"
            p.write_bytes(b"\xff\xd8data")
            imgs.append(p)

        dedup = _make_dedup()
        dedup.hasher.encode_image.return_value = "h"

        callback = MagicMock()
        dedup.batch_compute_hashes(imgs, progress_callback=callback)
        assert callback.call_count == 3
        callback.assert_any_call(1, 3)
        callback.assert_any_call(2, 3)
        callback.assert_any_call(3, 3)

    def test_no_callback(self, tmp_path: Path):
        """Test batch works without progress callback."""
        img = tmp_path / "only.jpg"
        img.write_bytes(b"\xff\xd8ok")

        dedup = _make_dedup()
        dedup.hasher.encode_image.return_value = "ok_hash"

        result = dedup.batch_compute_hashes([img])
        assert result == {img: "ok_hash"}


# ---------------------------------------------------------------------------
# _find_image_files
# ---------------------------------------------------------------------------
class TestFindImageFiles:
    """Test internal image file discovery."""

    def test_finds_supported_formats(self, tmp_path: Path):
        """Test discovery of all supported formats."""
        extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"]
        for ext in extensions:
            (tmp_path / f"image{ext}").write_bytes(b"\x00")

        dedup = _make_dedup()
        found = dedup._find_image_files(tmp_path)
        assert len(found) == len(extensions)

    def test_ignores_non_image_files(self, tmp_path: Path):
        """Test that non-image files are excluded."""
        (tmp_path / "doc.txt").write_text("hello")
        (tmp_path / "data.csv").write_text("a,b")
        (tmp_path / "image.jpg").write_bytes(b"\xff\xd8data")

        dedup = _make_dedup()
        found = dedup._find_image_files(tmp_path)
        assert len(found) == 1
        assert found[0].name == "image.jpg"

    def test_recursive_true(self, tmp_path: Path):
        """Test recursive scanning finds nested images."""
        subdir = tmp_path / "sub" / "deep"
        subdir.mkdir(parents=True)
        (subdir / "nested.png").write_bytes(b"\x89PNG")
        (tmp_path / "root.jpg").write_bytes(b"\xff\xd8")

        dedup = _make_dedup()
        found = dedup._find_image_files(tmp_path, recursive=True)
        assert len(found) == 2

    def test_recursive_false(self, tmp_path: Path):
        """Test non-recursive scanning ignores subdirectories."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "nested.png").write_bytes(b"\x89PNG")
        (tmp_path / "root.jpg").write_bytes(b"\xff\xd8")

        dedup = _make_dedup()
        found = dedup._find_image_files(tmp_path, recursive=False)
        assert len(found) == 1
        assert found[0].name == "root.jpg"

    def test_empty_directory(self, tmp_path: Path):
        """Test empty directory returns empty list."""
        dedup = _make_dedup()
        assert dedup._find_image_files(tmp_path) == []

    def test_ignores_directories_matching_extensions(self, tmp_path: Path):
        """Test that directories with image-like names are ignored."""
        (tmp_path / "photos.jpg").mkdir()
        dedup = _make_dedup()
        assert dedup._find_image_files(tmp_path) == []

    def test_case_insensitive_extensions(self, tmp_path: Path):
        """Test that uppercase extensions are matched."""
        (tmp_path / "photo.JPG").write_bytes(b"\xff\xd8data")
        (tmp_path / "image.PNG").write_bytes(b"\x89PNGdata")

        dedup = _make_dedup()
        found = dedup._find_image_files(tmp_path)
        assert len(found) == 2


# ---------------------------------------------------------------------------
# validate_image
# ---------------------------------------------------------------------------
class TestValidateImage:
    """Test image validation checks."""

    def test_valid_image(self, tmp_path: Path):
        """Test validation passes for a readable image."""
        img = tmp_path / "valid.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0data")

        dedup = _make_dedup()
        with patch(
            "file_organizer.services.deduplication.image_dedup.Image"
        ) as mock_image:
            mock_ctx = MagicMock()
            mock_image.open.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_image.open.return_value.__exit__ = MagicMock(return_value=False)

            is_valid, error = dedup.validate_image(img)
            assert is_valid is True
            assert error is None

    def test_nonexistent_file(self, tmp_path: Path):
        """Test validation fails for missing file."""
        dedup = _make_dedup()
        is_valid, error = dedup.validate_image(tmp_path / "nope.jpg")
        assert is_valid is False
        assert "File not found" in error

    def test_directory_instead_of_file(self, tmp_path: Path):
        """Test validation fails for directory."""
        dedup = _make_dedup()
        is_valid, error = dedup.validate_image(tmp_path)
        assert is_valid is False
        assert "not a file" in error

    def test_unsupported_format(self, tmp_path: Path):
        """Test validation fails for unsupported extension."""
        svg = tmp_path / "drawing.svg"
        svg.write_text("<svg></svg>")

        dedup = _make_dedup()
        is_valid, error = dedup.validate_image(svg)
        assert is_valid is False
        assert "Unsupported format" in error

    def test_corrupt_image_os_error(self, tmp_path: Path):
        """Test validation fails for corrupt image (PIL raises OSError)."""
        img = tmp_path / "corrupt.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0corrupt")

        dedup = _make_dedup()
        with patch(
            "file_organizer.services.deduplication.image_dedup.Image"
        ) as mock_image:
            mock_image.open.return_value.__enter__ = MagicMock(
                side_effect=OSError("truncated")
            )
            mock_image.open.return_value.__exit__ = MagicMock(return_value=False)

            is_valid, error = dedup.validate_image(img)
            assert is_valid is False
            assert "Cannot read image" in error

    def test_corrupt_image_generic_exception(self, tmp_path: Path):
        """Test validation fails for generically corrupt image."""
        img = tmp_path / "bad.png"
        img.write_bytes(b"\x89PNGbaddata")

        dedup = _make_dedup()
        with patch(
            "file_organizer.services.deduplication.image_dedup.Image"
        ) as mock_image:
            mock_image.open.return_value.__enter__ = MagicMock(
                side_effect=Exception("weird error")
            )
            mock_image.open.return_value.__exit__ = MagicMock(return_value=False)

            is_valid, error = dedup.validate_image(img)
            assert is_valid is False
            assert "Corrupt or invalid image" in error
