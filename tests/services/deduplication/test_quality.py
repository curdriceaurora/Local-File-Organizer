"""Tests for ImageQualityAnalyzer, QualityMetrics, and ImageFormat.

Tests quality scoring, comparison, ranking, crop detection, and
fallback behavior when PIL is unavailable.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.services.deduplication.quality import (
    ImageFormat,
    ImageQualityAnalyzer,
    QualityMetrics,
)

# ---------------------------------------------------------------------------
# ImageFormat enum
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestImageFormat:
    """Test the ImageFormat IntEnum ranking."""

    def test_ordering(self):
        """Formats are ordered from lowest to highest quality."""
        assert ImageFormat.UNKNOWN < ImageFormat.GIF
        assert ImageFormat.GIF < ImageFormat.BMP
        assert ImageFormat.BMP < ImageFormat.JPEG
        assert ImageFormat.JPEG < ImageFormat.WEBP
        assert ImageFormat.WEBP < ImageFormat.PNG
        assert ImageFormat.PNG < ImageFormat.TIFF

    def test_values(self):
        """Specific numeric values are assigned."""
        assert ImageFormat.UNKNOWN == 0
        assert ImageFormat.TIFF == 6


# ---------------------------------------------------------------------------
# QualityMetrics dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestQualityMetrics:
    """Test QualityMetrics dataclass and its to_dict method."""

    @pytest.fixture()
    def sample_metrics(self):
        return QualityMetrics(
            resolution=1920 * 1080,
            width=1920,
            height=1080,
            file_size=500_000,
            format=ImageFormat.JPEG,
            aspect_ratio=1920 / 1080,
            is_compressed=True,
            has_transparency=False,
            color_depth=24,
            modification_time=1700000000.0,
        )

    def test_to_dict_keys(self, sample_metrics):
        """to_dict includes all expected keys."""
        d = sample_metrics.to_dict()
        expected_keys = {
            "resolution",
            "width",
            "height",
            "file_size",
            "format",
            "aspect_ratio",
            "is_compressed",
            "has_transparency",
            "color_depth",
            "modification_time",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_format_is_name(self, sample_metrics):
        """Format should be serialized as the enum name, not integer."""
        d = sample_metrics.to_dict()
        assert d["format"] == "JPEG"

    def test_to_dict_values(self, sample_metrics):
        """Spot-check representative values."""
        d = sample_metrics.to_dict()
        assert d["resolution"] == 1920 * 1080
        assert d["file_size"] == 500_000
        assert d["is_compressed"] is True
        assert d["has_transparency"] is False


# ---------------------------------------------------------------------------
# ImageQualityAnalyzer — initialization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestImageQualityAnalyzerInit:
    """Test analyzer initialization and weight validation."""

    def test_default_weights(self):
        """Default weights are applied when none are provided."""
        analyzer = ImageQualityAnalyzer()
        assert analyzer.weights == ImageQualityAnalyzer.DEFAULT_WEIGHTS

    def test_custom_weights_valid(self):
        """Custom weights that sum to 1.0 are accepted."""
        custom = {
            "resolution": 0.5,
            "format": 0.2,
            "file_size": 0.1,
            "color_depth": 0.1,
            "has_transparency": 0.1,
        }
        analyzer = ImageQualityAnalyzer(weights=custom)
        assert analyzer.weights == custom

    def test_custom_weights_invalid_sum(self):
        """Weights that don't sum to ~1.0 raise ValueError."""
        bad = {
            "resolution": 0.5,
            "format": 0.5,
            "file_size": 0.5,
            "color_depth": 0.1,
            "has_transparency": 0.1,
        }
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            ImageQualityAnalyzer(weights=bad)

    def test_pil_available(self):
        """When PIL is available, _pil_available is True."""
        analyzer = ImageQualityAnalyzer()
        assert analyzer._pil_available is True

    def test_pil_not_available(self):
        """When PIL import fails, analyzer gracefully degrades."""
        analyzer = ImageQualityAnalyzer()
        # Simulate PIL being unavailable after construction
        analyzer._pil_available = False
        analyzer.Image = None
        assert analyzer._pil_available is False
        # Verify basic fallback still works
        assert analyzer.weights == ImageQualityAnalyzer.DEFAULT_WEIGHTS


# ---------------------------------------------------------------------------
# _get_format_from_extension
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFormatFromExtension:
    """Test format detection from file extensions."""

    @pytest.fixture()
    def analyzer(self):
        return ImageQualityAnalyzer()

    @pytest.mark.parametrize(
        "suffix,expected",
        [
            (".jpg", ImageFormat.JPEG),
            (".jpeg", ImageFormat.JPEG),
            (".JPG", ImageFormat.JPEG),
            (".png", ImageFormat.PNG),
            (".PNG", ImageFormat.PNG),
            (".gif", ImageFormat.GIF),
            (".bmp", ImageFormat.BMP),
            (".webp", ImageFormat.WEBP),
            (".tif", ImageFormat.TIFF),
            (".tiff", ImageFormat.TIFF),
        ],
    )
    def test_known_extensions(self, analyzer, suffix, expected):
        """Known image extensions map to the correct ImageFormat."""
        assert analyzer._get_format_from_extension(Path(f"image{suffix}")) == expected

    def test_unknown_extension(self, analyzer):
        """Unknown extension returns UNKNOWN."""
        assert analyzer._get_format_from_extension(Path("file.xyz")) == ImageFormat.UNKNOWN


# ---------------------------------------------------------------------------
# _extract_metrics_basic (fallback path, no PIL)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractMetricsBasic:
    """Test the fallback metrics extraction without PIL."""

    @pytest.fixture()
    def analyzer(self):
        return ImageQualityAnalyzer()

    def _create_file(self, tmp_path, name, size):
        """Helper to create a file of a given size."""
        p = tmp_path / name
        p.write_bytes(b"\x00" * size)
        return p

    def test_jpeg_basic_metrics(self, analyzer, tmp_path):
        """JPEG files use the JPEG compression estimate."""
        p = self._create_file(tmp_path, "photo.jpg", 10_000)
        m = analyzer._extract_metrics_basic(p)
        assert m.resolution == 10_000 * 10  # JPEG multiplier
        assert m.format == ImageFormat.JPEG
        assert m.is_compressed is True
        assert m.width == 0
        assert m.height == 0
        assert m.aspect_ratio == 1.0
        assert m.color_depth == 24

    def test_png_basic_metrics(self, analyzer, tmp_path):
        """PNG files use the PNG compression estimate."""
        p = self._create_file(tmp_path, "graphic.png", 20_000)
        m = analyzer._extract_metrics_basic(p)
        assert m.resolution == 20_000 * 3
        assert m.format == ImageFormat.PNG
        assert m.is_compressed is False
        assert m.has_transparency is True

    def test_gif_basic_metrics(self, analyzer, tmp_path):
        """GIF is marked as compressed and having transparency."""
        p = self._create_file(tmp_path, "anim.gif", 5_000)
        m = analyzer._extract_metrics_basic(p)
        assert m.format == ImageFormat.GIF
        assert m.is_compressed is True
        assert m.has_transparency is True

    def test_webp_basic_metrics(self, analyzer, tmp_path):
        """WEBP is marked as compressed and having transparency."""
        p = self._create_file(tmp_path, "modern.webp", 8_000)
        m = analyzer._extract_metrics_basic(p)
        assert m.format == ImageFormat.WEBP
        assert m.is_compressed is True
        assert m.has_transparency is True

    def test_bmp_basic_metrics(self, analyzer, tmp_path):
        """BMP uses the default pixel estimate multiplier."""
        p = self._create_file(tmp_path, "raw.bmp", 12_000)
        m = analyzer._extract_metrics_basic(p)
        assert m.resolution == 12_000 * 5  # default multiplier
        assert m.format == ImageFormat.BMP
        assert m.is_compressed is False
        assert m.has_transparency is False

    def test_unknown_format_basic(self, analyzer, tmp_path):
        """Unknown formats use the default multiplier."""
        p = self._create_file(tmp_path, "data.xyz", 7_000)
        m = analyzer._extract_metrics_basic(p)
        assert m.resolution == 7_000 * 5
        assert m.format == ImageFormat.UNKNOWN

    def test_modification_time_populated(self, analyzer, tmp_path):
        """modification_time comes from the file's mtime."""
        p = self._create_file(tmp_path, "test.jpg", 100)
        m = analyzer._extract_metrics_basic(p)
        assert m.modification_time > 0


# ---------------------------------------------------------------------------
# _extract_metrics_with_pil
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractMetricsWithPil:
    """Test PIL-based metrics extraction using mocked PIL Image."""

    @pytest.fixture()
    def analyzer(self):
        return ImageQualityAnalyzer()

    def test_returns_none_when_pil_unavailable(self, analyzer, tmp_path):
        """When PIL is unavailable, returns None."""
        analyzer._pil_available = False
        p = tmp_path / "img.png"
        p.write_bytes(b"\x00")
        assert analyzer._extract_metrics_with_pil(p) is None

    def test_successful_extraction(self, analyzer, tmp_path):
        """Successful PIL extraction returns correct QualityMetrics."""
        p = tmp_path / "photo.jpg"
        p.write_bytes(b"\x00" * 5_000)

        mock_img = MagicMock()
        mock_img.size = (1920, 1080)
        mock_img.format = "JPEG"
        mock_img.mode = "RGB"
        mock_img.info = {}
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        analyzer.Image = MagicMock()
        analyzer.Image.open.return_value = mock_img

        m = analyzer._extract_metrics_with_pil(p)
        assert m is not None
        assert m.width == 1920
        assert m.height == 1080
        assert m.resolution == 1920 * 1080
        assert m.is_compressed is True  # JPEG
        assert m.has_transparency is False  # RGB
        assert m.color_depth == 24
        assert m.format == ImageFormat.JPEG
        assert m.aspect_ratio == pytest.approx(1920 / 1080)

    def test_rgba_mode_has_transparency(self, analyzer, tmp_path):
        """RGBA mode sets has_transparency to True."""
        p = tmp_path / "icon.png"
        p.write_bytes(b"\x00" * 1_000)

        mock_img = MagicMock()
        mock_img.size = (256, 256)
        mock_img.format = "PNG"
        mock_img.mode = "RGBA"
        mock_img.info = {}
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        analyzer.Image = MagicMock()
        analyzer.Image.open.return_value = mock_img

        m = analyzer._extract_metrics_with_pil(p)
        assert m.has_transparency is True
        assert m.color_depth == 32

    def test_palette_mode_with_transparency(self, analyzer, tmp_path):
        """Palette mode with transparency info is detected."""
        p = tmp_path / "palette.gif"
        p.write_bytes(b"\x00" * 500)

        mock_img = MagicMock()
        mock_img.size = (100, 100)
        mock_img.format = "GIF"
        mock_img.mode = "P"
        mock_img.info = {"transparency": 0}
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        analyzer.Image = MagicMock()
        analyzer.Image.open.return_value = mock_img

        m = analyzer._extract_metrics_with_pil(p)
        assert m.has_transparency is True
        assert m.color_depth == 8  # P mode

    def test_la_mode_has_transparency(self, analyzer, tmp_path):
        """LA mode (grayscale + alpha) sets transparency."""
        p = tmp_path / "gray.png"
        p.write_bytes(b"\x00" * 200)

        mock_img = MagicMock()
        mock_img.size = (50, 50)
        mock_img.format = "PNG"
        mock_img.mode = "LA"
        mock_img.info = {}
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        analyzer.Image = MagicMock()
        analyzer.Image.open.return_value = mock_img

        m = analyzer._extract_metrics_with_pil(p)
        assert m.has_transparency is True

    def test_unknown_mode_defaults_to_24_bit(self, analyzer, tmp_path):
        """Unknown image mode defaults to 24-bit color depth."""
        p = tmp_path / "strange.tiff"
        p.write_bytes(b"\x00" * 300)

        mock_img = MagicMock()
        mock_img.size = (80, 60)
        mock_img.format = "TIFF"
        mock_img.mode = "WEIRD_MODE"
        mock_img.info = {}
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        analyzer.Image = MagicMock()
        analyzer.Image.open.return_value = mock_img

        m = analyzer._extract_metrics_with_pil(p)
        assert m.color_depth == 24

    def test_height_zero_aspect_ratio(self, analyzer, tmp_path):
        """Height=0 yields aspect_ratio=0 to avoid division by zero."""
        p = tmp_path / "degenerate.png"
        p.write_bytes(b"\x00" * 100)

        mock_img = MagicMock()
        mock_img.size = (100, 0)
        mock_img.format = "PNG"
        mock_img.mode = "RGB"
        mock_img.info = {}
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        analyzer.Image = MagicMock()
        analyzer.Image.open.return_value = mock_img

        m = analyzer._extract_metrics_with_pil(p)
        assert m.aspect_ratio == 0

    def test_exception_returns_none(self, analyzer, tmp_path):
        """If PIL raises, returns None instead of crashing."""
        p = tmp_path / "corrupt.jpg"
        p.write_bytes(b"\x00" * 100)

        analyzer.Image = MagicMock()
        analyzer.Image.open.side_effect = OSError("Corrupt image")

        m = analyzer._extract_metrics_with_pil(p)
        assert m is None

    def test_webp_format_is_compressed(self, analyzer, tmp_path):
        """WEBP format is correctly flagged as compressed."""
        p = tmp_path / "photo.webp"
        p.write_bytes(b"\x00" * 2_000)

        mock_img = MagicMock()
        mock_img.size = (640, 480)
        mock_img.format = "WEBP"
        mock_img.mode = "RGB"
        mock_img.info = {}
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        analyzer.Image = MagicMock()
        analyzer.Image.open.return_value = mock_img

        m = analyzer._extract_metrics_with_pil(p)
        assert m.is_compressed is True

    def test_png_format_not_compressed(self, analyzer, tmp_path):
        """PNG format is correctly flagged as not compressed."""
        p = tmp_path / "lossless.png"
        p.write_bytes(b"\x00" * 2_000)

        mock_img = MagicMock()
        mock_img.size = (640, 480)
        mock_img.format = "PNG"
        mock_img.mode = "RGB"
        mock_img.info = {}
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        analyzer.Image = MagicMock()
        analyzer.Image.open.return_value = mock_img

        m = analyzer._extract_metrics_with_pil(p)
        assert m.is_compressed is False


# ---------------------------------------------------------------------------
# get_quality_metrics
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetQualityMetrics:
    """Test the public quality metrics entry point."""

    @pytest.fixture()
    def analyzer(self):
        return ImageQualityAnalyzer()

    def test_nonexistent_file_returns_none(self, analyzer, tmp_path):
        """Missing files return None."""
        result = analyzer.get_quality_metrics(tmp_path / "nope.jpg")
        assert result is None

    def test_falls_back_to_basic_when_pil_fails(self, analyzer, tmp_path):
        """When PIL extraction returns None, basic is used as fallback."""
        p = tmp_path / "test.jpg"
        p.write_bytes(b"\x00" * 1_000)
        analyzer._pil_available = False

        m = analyzer.get_quality_metrics(p)
        assert m is not None
        assert m.width == 0  # basic fallback has no width info

    def test_pil_extraction_used_when_available(self, analyzer, tmp_path):
        """When PIL succeeds, its metrics are used."""
        p = tmp_path / "real.png"
        p.write_bytes(b"\x00" * 500)

        mock_img = MagicMock()
        mock_img.size = (800, 600)
        mock_img.format = "PNG"
        mock_img.mode = "RGB"
        mock_img.info = {}
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        analyzer.Image = MagicMock()
        analyzer.Image.open.return_value = mock_img

        m = analyzer.get_quality_metrics(p)
        assert m is not None
        assert m.width == 800
        assert m.height == 600


# ---------------------------------------------------------------------------
# _score_from_metrics  &  assess_quality
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScoring:
    """Test quality scoring logic."""

    @pytest.fixture()
    def analyzer(self):
        return ImageQualityAnalyzer()

    def _make_metrics(self, **overrides):
        """Helper to create QualityMetrics with sensible defaults."""
        defaults = {
            "resolution": 1_000_000,
            "width": 1000,
            "height": 1000,
            "file_size": 500_000,
            "format": ImageFormat.JPEG,
            "aspect_ratio": 1.0,
            "is_compressed": True,
            "has_transparency": False,
            "color_depth": 24,
            "modification_time": 1700000000.0,
        }
        defaults.update(overrides)
        return QualityMetrics(**defaults)

    def test_score_range(self, analyzer):
        """Score is between 0.0 and 1.0."""
        m = self._make_metrics()
        s = analyzer._score_from_metrics(m)
        assert 0.0 <= s <= 1.0

    def test_higher_resolution_higher_score(self, analyzer):
        """Higher resolution should produce a higher score."""
        low = self._make_metrics(resolution=100_000)
        high = self._make_metrics(resolution=10_000_000)
        assert analyzer._score_from_metrics(high) > analyzer._score_from_metrics(low)

    def test_resolution_caps_at_max(self, analyzer):
        """Resolution above 25M pixels caps at 1.0 contribution."""
        capped = self._make_metrics(resolution=50_000_000)
        at_max = self._make_metrics(resolution=25_000_000)
        # They should have the same resolution score component
        s1 = analyzer._score_from_metrics(capped)
        s2 = analyzer._score_from_metrics(at_max)
        assert s1 == pytest.approx(s2, abs=0.001)

    def test_better_format_higher_score(self, analyzer):
        """TIFF should score higher than GIF (format component)."""
        gif = self._make_metrics(format=ImageFormat.GIF)
        tiff = self._make_metrics(format=ImageFormat.TIFF)
        assert analyzer._score_from_metrics(tiff) > analyzer._score_from_metrics(gif)

    def test_larger_file_higher_score(self, analyzer):
        """Larger file size contributes to higher score."""
        small = self._make_metrics(file_size=10_000)
        large = self._make_metrics(file_size=10_000_000)
        assert analyzer._score_from_metrics(large) > analyzer._score_from_metrics(small)

    def test_higher_color_depth_higher_score(self, analyzer):
        """Higher color depth should contribute to higher score."""
        low_depth = self._make_metrics(color_depth=8)
        high_depth = self._make_metrics(color_depth=32)
        assert analyzer._score_from_metrics(high_depth) > analyzer._score_from_metrics(low_depth)

    def test_transparency_bonus(self, analyzer):
        """has_transparency=True adds a bonus to the score."""
        no_alpha = self._make_metrics(has_transparency=False)
        alpha = self._make_metrics(has_transparency=True)
        assert analyzer._score_from_metrics(alpha) > analyzer._score_from_metrics(no_alpha)

    def test_assess_quality_returns_zero_for_missing(self, analyzer, tmp_path):
        """assess_quality returns 0.0 for nonexistent files."""
        s = analyzer.assess_quality(tmp_path / "missing.png")
        assert s == 0.0

    def test_assess_quality_returns_positive_for_file(self, analyzer, tmp_path):
        """assess_quality returns positive for a valid file (basic fallback)."""
        p = tmp_path / "test.jpg"
        p.write_bytes(b"\x00" * 1_000)
        analyzer._pil_available = False
        s = analyzer.assess_quality(p)
        assert s > 0.0

    def test_file_size_caps_at_max(self, analyzer):
        """File size above 50 MB caps at 1.0 contribution."""
        huge = self._make_metrics(file_size=100_000_000)
        at_max = self._make_metrics(file_size=50_000_000)
        s1 = analyzer._score_from_metrics(huge)
        s2 = analyzer._score_from_metrics(at_max)
        assert s1 == pytest.approx(s2, abs=0.001)


# ---------------------------------------------------------------------------
# compare_quality
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCompareQuality:
    """Test pairwise quality comparison."""

    @pytest.fixture()
    def analyzer(self):
        a = ImageQualityAnalyzer()
        a._pil_available = False  # use basic fallback for speed
        return a

    def test_larger_jpeg_wins(self, analyzer, tmp_path):
        """Larger JPEG should be considered better quality."""
        small = tmp_path / "small.jpg"
        large = tmp_path / "large.jpg"
        small.write_bytes(b"\x00" * 1_000)
        large.write_bytes(b"\x00" * 100_000)

        result = analyzer.compare_quality(large, small)
        assert result == -1  # first (large) is better

    def test_equal_files(self, analyzer, tmp_path):
        """Identical files should compare as equal."""
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        a.write_bytes(b"\x00" * 5_000)
        b.write_bytes(b"\x00" * 5_000)

        result = analyzer.compare_quality(a, b)
        assert result == 0

    def test_second_is_better(self, analyzer, tmp_path):
        """When second image is better, returns 1."""
        worse = tmp_path / "worse.jpg"
        better = tmp_path / "better.jpg"
        worse.write_bytes(b"\x00" * 500)
        better.write_bytes(b"\x00" * 500_000)

        result = analyzer.compare_quality(worse, better)
        assert result == 1

    def test_missing_file_scores_zero(self, analyzer, tmp_path):
        """Missing file scores 0, so the existing file wins."""
        exists = tmp_path / "exists.jpg"
        exists.write_bytes(b"\x00" * 10_000)
        missing = tmp_path / "missing.jpg"

        result = analyzer.compare_quality(exists, missing)
        assert result == -1  # existing is better


# ---------------------------------------------------------------------------
# get_best_quality
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetBestQuality:
    """Test selecting the best quality image from a list."""

    @pytest.fixture()
    def analyzer(self):
        a = ImageQualityAnalyzer()
        a._pil_available = False
        return a

    def test_empty_list(self, analyzer):
        """Empty list returns None."""
        assert analyzer.get_best_quality([]) is None

    def test_single_image(self, analyzer, tmp_path):
        """Single image is returned directly."""
        p = tmp_path / "only.jpg"
        p.write_bytes(b"\x00" * 100)
        assert analyzer.get_best_quality([p]) == p

    def test_selects_largest(self, analyzer, tmp_path):
        """Largest file (higher score) is selected."""
        small = tmp_path / "small.jpg"
        medium = tmp_path / "medium.jpg"
        large = tmp_path / "large.jpg"
        small.write_bytes(b"\x00" * 1_000)
        medium.write_bytes(b"\x00" * 10_000)
        large.write_bytes(b"\x00" * 100_000)

        best = analyzer.get_best_quality([small, medium, large])
        assert best == large

    def test_all_assessments_fail(self, analyzer, tmp_path):
        """When all assessments fail, returns first image as fallback."""
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        # Files don't exist, so all assessments score 0
        # But get_quality_metrics returns None for missing files,
        # which makes assess_quality return 0.0
        # The method filters score > 0, so valid_images is empty,
        # and it falls back to returning images[0]
        result = analyzer.get_best_quality([a, b])
        assert result == a

    def test_png_beats_gif_same_size(self, analyzer, tmp_path):
        """PNG format advantage beats GIF at same file size."""
        gif = tmp_path / "anim.gif"
        png = tmp_path / "image.png"
        gif.write_bytes(b"\x00" * 10_000)
        png.write_bytes(b"\x00" * 10_000)

        best = analyzer.get_best_quality([gif, png])
        assert best == png


# ---------------------------------------------------------------------------
# is_likely_cropped
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsLikelyCropped:
    """Test crop detection heuristic."""

    @pytest.fixture()
    def analyzer(self):
        return ImageQualityAnalyzer()

    def _mock_metrics(self, analyzer, mapping):
        """Patch get_quality_metrics to return predetermined values."""

        def fake_get(path):
            return mapping.get(str(path))

        analyzer.get_quality_metrics = fake_get

    def _make_metrics(self, resolution, aspect_ratio, **kw):
        defaults = {
            "width": int(resolution**0.5),
            "height": int(resolution**0.5),
            "file_size": resolution // 3,
            "format": ImageFormat.JPEG,
            "is_compressed": True,
            "has_transparency": False,
            "color_depth": 24,
            "modification_time": 1700000000.0,
        }
        defaults.update(kw)
        return QualityMetrics(
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            **defaults,
        )

    def test_metrics_unavailable_returns_false(self, analyzer, tmp_path):
        """When metrics can't be extracted, return False."""
        orig = tmp_path / "orig.jpg"
        cand = tmp_path / "cand.jpg"
        # Files don't exist
        assert analyzer.is_likely_cropped(orig, cand) is False

    def test_candidate_larger_returns_false(self, analyzer):
        """If candidate has equal or larger resolution, not a crop."""
        orig = Path("/fake/orig.jpg")
        cand = Path("/fake/cand.jpg")
        self._mock_metrics(
            analyzer,
            {
                str(orig): self._make_metrics(1_000_000, 1.5),
                str(cand): self._make_metrics(2_000_000, 1.5),
            },
        )
        assert analyzer.is_likely_cropped(orig, cand) is False

    def test_different_aspect_ratio_is_crop(self, analyzer):
        """Large aspect ratio difference with smaller resolution = crop."""
        orig = Path("/fake/orig.jpg")
        cand = Path("/fake/cand.jpg")
        self._mock_metrics(
            analyzer,
            {
                str(orig): self._make_metrics(1_000_000, 1.78),
                str(cand): self._make_metrics(500_000, 1.33),
            },
        )
        assert analyzer.is_likely_cropped(orig, cand) is True

    def test_proportional_resize_not_crop(self, analyzer):
        """Resolution reduced proportionally with same aspect = resize, not crop."""
        orig = Path("/fake/orig.jpg")
        cand = Path("/fake/cand.jpg")
        # ratio = 900_000 / 1_000_000 = 0.9 > threshold (0.8)
        # aspect_diff = 0 < 0.1
        self._mock_metrics(
            analyzer,
            {
                str(orig): self._make_metrics(1_000_000, 1.5),
                str(cand): self._make_metrics(900_000, 1.5),
            },
        )
        assert analyzer.is_likely_cropped(orig, cand) is False

    def test_small_resolution_moderate_aspect_is_crop(self, analyzer):
        """Smaller resolution + moderate aspect change = likely crop."""
        orig = Path("/fake/orig.jpg")
        cand = Path("/fake/cand.jpg")
        # ratio = 600_000 / 1_000_000 = 0.6 < threshold (0.8)
        # aspect_diff = 0.1 > 0.05
        self._mock_metrics(
            analyzer,
            {
                str(orig): self._make_metrics(1_000_000, 1.5),
                str(cand): self._make_metrics(600_000, 1.4),
            },
        )
        assert analyzer.is_likely_cropped(orig, cand) is True

    def test_small_resolution_tiny_aspect_diff_not_crop(self, analyzer):
        """Smaller resolution but very similar aspect ratio = ambiguous, returns False."""
        orig = Path("/fake/orig.jpg")
        cand = Path("/fake/cand.jpg")
        # ratio = 600_000 / 1_000_000 = 0.6 < threshold (0.8)
        # aspect_diff = 0.02 < 0.05
        self._mock_metrics(
            analyzer,
            {
                str(orig): self._make_metrics(1_000_000, 1.50),
                str(cand): self._make_metrics(600_000, 1.48),
            },
        )
        assert analyzer.is_likely_cropped(orig, cand) is False

    def test_one_missing_metric_returns_false(self, analyzer):
        """If only one image has metrics, returns False."""
        orig = Path("/fake/orig.jpg")
        cand = Path("/fake/cand.jpg")
        self._mock_metrics(
            analyzer,
            {
                str(orig): self._make_metrics(1_000_000, 1.5),
                str(cand): None,
            },
        )
        assert analyzer.is_likely_cropped(orig, cand) is False

    def test_custom_threshold(self, analyzer):
        """Custom threshold parameter is respected."""
        orig = Path("/fake/orig.jpg")
        cand = Path("/fake/cand.jpg")
        # ratio = 700_000 / 1_000_000 = 0.7
        # With default threshold=0.8, ratio < threshold so it checks further
        # aspect_diff = 0.08 > 0.05, so it's a crop
        self._mock_metrics(
            analyzer,
            {
                str(orig): self._make_metrics(1_000_000, 1.5),
                str(cand): self._make_metrics(700_000, 1.42),
            },
        )
        # With threshold=0.6, ratio 0.7 > threshold and aspect_diff 0.08 < 0.1
        # so it returns False (looks like resize)
        assert analyzer.is_likely_cropped(orig, cand, threshold=0.6) is False

        # With threshold=0.8 (default), ratio 0.7 < threshold and aspect_diff > 0.05
        # so it returns True (looks like crop)
        assert analyzer.is_likely_cropped(orig, cand, threshold=0.8) is True


# ---------------------------------------------------------------------------
# get_ranked_images
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetRankedImages:
    """Test image ranking functionality."""

    @pytest.fixture()
    def analyzer(self):
        a = ImageQualityAnalyzer()
        a._pil_available = False
        return a

    def test_empty_list(self, analyzer):
        """Empty list returns empty ranking."""
        assert analyzer.get_ranked_images([]) == []

    def test_ranking_order(self, analyzer, tmp_path):
        """Images are ranked best-first (descending score)."""
        small = tmp_path / "small.jpg"
        large = tmp_path / "large.jpg"
        small.write_bytes(b"\x00" * 1_000)
        large.write_bytes(b"\x00" * 100_000)

        ranked = analyzer.get_ranked_images([small, large])
        assert len(ranked) == 2
        assert ranked[0][0] == large  # best first
        assert ranked[1][0] == small

    def test_result_tuples_structure(self, analyzer, tmp_path):
        """Each result is a tuple of (Path, float, QualityMetrics)."""
        p = tmp_path / "img.jpg"
        p.write_bytes(b"\x00" * 5_000)

        ranked = analyzer.get_ranked_images([p])
        assert len(ranked) == 1
        path, score, metrics = ranked[0]
        assert path == p
        assert isinstance(score, float)
        assert isinstance(metrics, QualityMetrics)

    def test_missing_files_excluded(self, analyzer, tmp_path):
        """Missing files are excluded from ranking."""
        exists = tmp_path / "exists.jpg"
        exists.write_bytes(b"\x00" * 5_000)
        missing = tmp_path / "missing.jpg"

        ranked = analyzer.get_ranked_images([exists, missing])
        assert len(ranked) == 1
        assert ranked[0][0] == exists

    def test_multiple_formats_ranked(self, analyzer, tmp_path):
        """Different formats are ranked considering format bonus."""
        gif = tmp_path / "anim.gif"
        png = tmp_path / "image.png"
        gif.write_bytes(b"\x00" * 10_000)
        png.write_bytes(b"\x00" * 10_000)

        ranked = analyzer.get_ranked_images([gif, png])
        assert len(ranked) == 2
        # PNG should rank higher than GIF at same size
        assert ranked[0][0] == png
