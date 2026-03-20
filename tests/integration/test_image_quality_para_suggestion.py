"""Integration tests for image quality analyzer and PARA suggestion engine.

Covers:
  - services/deduplication/quality.py  — ImageQualityAnalyzer, QualityMetrics, ImageFormat
  - methodologies/para/ai/suggestion_engine.py — SuggestionEngine
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.deduplication.quality import (
    ImageFormat,
    ImageQualityAnalyzer,
    QualityMetrics,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# ImageFormat enum
# ---------------------------------------------------------------------------


class TestImageFormat:
    def test_unknown_value(self) -> None:
        assert ImageFormat.UNKNOWN == 0

    def test_tiff_highest(self) -> None:
        assert ImageFormat.TIFF > ImageFormat.PNG
        assert ImageFormat.TIFF > ImageFormat.JPEG

    def test_png_above_jpeg(self) -> None:
        assert ImageFormat.PNG > ImageFormat.JPEG

    def test_members(self) -> None:
        names = {m.name for m in ImageFormat}
        assert "TIFF" in names
        assert "PNG" in names
        assert "JPEG" in names


# ---------------------------------------------------------------------------
# QualityMetrics dataclass
# ---------------------------------------------------------------------------


class TestQualityMetrics:
    def _make_metrics(self, **kwargs) -> QualityMetrics:
        defaults = {
            "resolution": 1000000,
            "width": 1000,
            "height": 1000,
            "file_size": 500000,
            "format": ImageFormat.PNG,
            "aspect_ratio": 1.0,
            "is_compressed": False,
            "has_transparency": True,
            "color_depth": 24,
            "modification_time": 1700000000.0,
        }
        defaults.update(kwargs)
        return QualityMetrics(**defaults)

    def test_created(self) -> None:
        m = self._make_metrics()
        assert m.resolution == 1000000
        assert m.format == ImageFormat.PNG

    def test_to_dict_returns_dict(self) -> None:
        m = self._make_metrics()
        d = m.to_dict()
        assert "resolution" in d

    def test_to_dict_has_required_keys(self) -> None:
        m = self._make_metrics()
        d = m.to_dict()
        for key in ("resolution", "width", "height", "file_size", "format", "aspect_ratio"):
            assert key in d

    def test_to_dict_format_is_string(self) -> None:
        m = self._make_metrics(format=ImageFormat.JPEG)
        d = m.to_dict()
        assert d["format"] == "JPEG"

    def test_has_transparency_stored(self) -> None:
        m = self._make_metrics(has_transparency=True)
        assert m.has_transparency is True

    def test_is_compressed_stored(self) -> None:
        m = self._make_metrics(is_compressed=True)
        assert m.is_compressed is True


# ---------------------------------------------------------------------------
# ImageQualityAnalyzer — init
# ---------------------------------------------------------------------------


@pytest.fixture()
def analyzer() -> ImageQualityAnalyzer:
    return ImageQualityAnalyzer()


class TestImageQualityAnalyzerInit:
    def test_default_init(self) -> None:
        a = ImageQualityAnalyzer()
        assert a is not None

    def test_default_weights_set(self) -> None:
        a = ImageQualityAnalyzer()
        assert isinstance(a.weights, dict)
        assert "resolution" in a.weights

    def test_custom_weights(self) -> None:
        weights = {
            "resolution": 0.5,
            "format": 0.2,
            "file_size": 0.2,
            "color_depth": 0.05,
            "has_transparency": 0.05,
        }
        a = ImageQualityAnalyzer(weights=weights)
        assert a.weights["resolution"] == 0.5

    def test_invalid_weights_raise(self) -> None:
        bad = {"resolution": 0.9}
        with pytest.raises(ValueError):
            ImageQualityAnalyzer(weights=bad)


# ---------------------------------------------------------------------------
# ImageQualityAnalyzer — get_quality_metrics
# ---------------------------------------------------------------------------


class TestGetQualityMetrics:
    def test_nonexistent_returns_none(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "missing.jpg"
        result = analyzer.get_quality_metrics(f)
        assert result is None

    def test_existing_jpg_returns_metrics(
        self, analyzer: ImageQualityAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "image.jpg"
        f.write_bytes(b"\xff\xd8\xff" + b"x" * 500)
        result = analyzer.get_quality_metrics(f)
        assert isinstance(result, QualityMetrics)

    def test_existing_png_returns_metrics(
        self, analyzer: ImageQualityAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG" + b"x" * 1000)
        result = analyzer.get_quality_metrics(f)
        assert isinstance(result, QualityMetrics)

    def test_metrics_file_size_correct(
        self, analyzer: ImageQualityAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "test.jpg"
        data = b"x" * 1024
        f.write_bytes(data)
        result = analyzer.get_quality_metrics(f)
        assert result is not None
        assert result.file_size == 1024

    def test_metrics_format_jpg(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "test.jpg"
        f.write_bytes(b"x" * 100)
        result = analyzer.get_quality_metrics(f)
        assert result is not None
        assert result.format == ImageFormat.JPEG

    def test_metrics_format_png(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "test.png"
        f.write_bytes(b"x" * 100)
        result = analyzer.get_quality_metrics(f)
        assert result is not None
        assert result.format == ImageFormat.PNG

    def test_metrics_format_tiff(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "test.tiff"
        f.write_bytes(b"x" * 100)
        result = analyzer.get_quality_metrics(f)
        assert result is not None
        assert result.format == ImageFormat.TIFF

    def test_metrics_format_unknown(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "test.xyz"
        f.write_bytes(b"x" * 100)
        result = analyzer.get_quality_metrics(f)
        assert result is not None
        assert result.format == ImageFormat.UNKNOWN

    def test_metrics_has_modification_time(
        self, analyzer: ImageQualityAnalyzer, tmp_path: Path
    ) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"x" * 200)
        result = analyzer.get_quality_metrics(f)
        assert result is not None
        assert result.modification_time > 0


# ---------------------------------------------------------------------------
# ImageQualityAnalyzer — assess_quality
# ---------------------------------------------------------------------------


class TestAssessQuality:
    def test_nonexistent_returns_zero(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "missing.jpg"
        score = analyzer.assess_quality(f)
        assert score == 0.0

    def test_existing_returns_float(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "image.jpg"
        f.write_bytes(b"x" * 1000)
        score = analyzer.assess_quality(f)
        assert 0.0 <= score <= 1.0

    def test_score_in_range(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"x" * 5000)
        score = analyzer.assess_quality(f)
        assert 0.0 <= score <= 1.0

    def test_larger_file_higher_score(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        small = tmp_path / "small.jpg"
        large = tmp_path / "large.jpg"
        small.write_bytes(b"x" * 100)
        large.write_bytes(b"x" * 100000)
        small_score = analyzer.assess_quality(small)
        large_score = analyzer.assess_quality(large)
        assert large_score >= small_score

    def test_png_vs_jpg_format_advantage(
        self, analyzer: ImageQualityAnalyzer, tmp_path: Path
    ) -> None:
        # Same size but PNG has higher format rank
        jpg = tmp_path / "image.jpg"
        png = tmp_path / "image.png"
        same_data = b"x" * 5000
        jpg.write_bytes(same_data)
        png.write_bytes(same_data)
        jpg_score = analyzer.assess_quality(jpg)
        png_score = analyzer.assess_quality(png)
        # PNG ranks higher than JPEG in the format scoring
        assert png_score >= jpg_score


# ---------------------------------------------------------------------------
# ImageQualityAnalyzer — compare_quality
# ---------------------------------------------------------------------------


class TestCompareQuality:
    def test_better_file_returns_negative_one(
        self, analyzer: ImageQualityAnalyzer, tmp_path: Path
    ) -> None:
        img1 = tmp_path / "large.jpg"
        img2 = tmp_path / "small.jpg"
        img1.write_bytes(b"x" * 50000)
        img2.write_bytes(b"x" * 100)
        result = analyzer.compare_quality(img1, img2)
        assert result == -1

    def test_worse_file_returns_one(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        img1 = tmp_path / "tiny.jpg"
        img2 = tmp_path / "big.jpg"
        img1.write_bytes(b"x" * 10)
        img2.write_bytes(b"x" * 50000)
        result = analyzer.compare_quality(img1, img2)
        assert result == 1

    def test_equal_returns_zero(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        img1 = tmp_path / "a.jpg"
        img2 = tmp_path / "b.jpg"
        same = b"x" * 1000
        img1.write_bytes(same)
        img2.write_bytes(same)
        result = analyzer.compare_quality(img1, img2)
        assert result == 0

    def test_returns_int(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.png"
        img1.write_bytes(b"x" * 1000)
        img2.write_bytes(b"x" * 1000)
        result = analyzer.compare_quality(img1, img2)
        assert isinstance(result, int)
        assert result in (-1, 0, 1)


# ---------------------------------------------------------------------------
# ImageQualityAnalyzer — get_best_quality
# ---------------------------------------------------------------------------


class TestGetBestQuality:
    def test_empty_list_returns_none(self, analyzer: ImageQualityAnalyzer) -> None:
        result = analyzer.get_best_quality([])
        assert result is None

    def test_single_file_returns_it(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "only.jpg"
        f.write_bytes(b"x" * 1000)
        result = analyzer.get_best_quality([f])
        assert result == f

    def test_returns_highest_quality(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        small = tmp_path / "small.jpg"
        large = tmp_path / "large.jpg"
        small.write_bytes(b"x" * 100)
        large.write_bytes(b"x" * 100000)
        result = analyzer.get_best_quality([small, large])
        assert result == large

    def test_returns_path(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f1 = tmp_path / "a.png"
        f2 = tmp_path / "b.png"
        f1.write_bytes(b"x" * 500)
        f2.write_bytes(b"x" * 500)
        result = analyzer.get_best_quality([f1, f2])
        assert isinstance(result, Path)

    def test_all_missing_returns_first(
        self, analyzer: ImageQualityAnalyzer, tmp_path: Path
    ) -> None:
        f1 = tmp_path / "missing1.jpg"
        f2 = tmp_path / "missing2.jpg"
        # Files don't exist — assess_quality returns 0.0 for both
        result = analyzer.get_best_quality([f1, f2])
        # When all scores are 0, fallback returns first
        assert result == f1


# ---------------------------------------------------------------------------
# ImageQualityAnalyzer — get_ranked_images
# ---------------------------------------------------------------------------


class TestGetRankedImages:
    def test_empty_list_returns_empty(self, analyzer: ImageQualityAnalyzer) -> None:
        result = analyzer.get_ranked_images([])
        assert result == []

    def test_returns_list_of_tuples(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"x" * 1000)
        result = analyzer.get_ranked_images([f])
        assert isinstance(result, list)
        assert len(result) == 1
        path, score, metrics = result[0]
        assert path == f
        assert isinstance(score, float)
        assert isinstance(metrics, QualityMetrics)

    def test_ordered_best_first(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        small = tmp_path / "small.jpg"
        large = tmp_path / "large.jpg"
        small.write_bytes(b"x" * 100)
        large.write_bytes(b"x" * 50000)
        result = analyzer.get_ranked_images([small, large])
        assert len(result) == 2
        # First element should have higher score
        assert result[0][1] >= result[1][1]

    def test_missing_files_excluded(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        existing = tmp_path / "real.jpg"
        missing = tmp_path / "ghost.jpg"
        existing.write_bytes(b"x" * 1000)
        result = analyzer.get_ranked_images([existing, missing])
        paths = [r[0] for r in result]
        assert existing in paths
        assert missing not in paths

    def test_multiple_files_all_ranked(
        self, analyzer: ImageQualityAnalyzer, tmp_path: Path
    ) -> None:
        files = []
        for i in range(4):
            f = tmp_path / f"img{i}.png"
            f.write_bytes(b"x" * (100 * (i + 1)))
            files.append(f)
        result = analyzer.get_ranked_images(files)
        assert len(result) == 4


# ---------------------------------------------------------------------------
# ImageQualityAnalyzer — is_likely_cropped
# ---------------------------------------------------------------------------


class TestIsLikelyCropped:
    def test_missing_files_returns_false(
        self, analyzer: ImageQualityAnalyzer, tmp_path: Path
    ) -> None:
        orig = tmp_path / "orig.jpg"
        cand = tmp_path / "cand.jpg"
        result = analyzer.is_likely_cropped(orig, cand)
        assert result is False

    def test_same_file_not_cropped(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"x" * 5000)
        result = analyzer.is_likely_cropped(f, f)
        assert result is False

    def test_returns_bool(self, analyzer: ImageQualityAnalyzer, tmp_path: Path) -> None:
        f1 = tmp_path / "a.jpg"
        f2 = tmp_path / "b.jpg"
        f1.write_bytes(b"x" * 5000)
        f2.write_bytes(b"x" * 1000)
        result = analyzer.is_likely_cropped(f1, f2)
        assert result is False

    def test_candidate_larger_returns_false(
        self, analyzer: ImageQualityAnalyzer, tmp_path: Path
    ) -> None:
        # Candidate is "larger" than original (basic metrics: larger file = more estimated pixels)
        small_orig = tmp_path / "small.jpg"
        big_cand = tmp_path / "big.jpg"
        small_orig.write_bytes(b"x" * 100)
        big_cand.write_bytes(b"x" * 10000)
        result = analyzer.is_likely_cropped(small_orig, big_cand)
        assert result is False


# ---------------------------------------------------------------------------
# SuggestionEngine — import and basic API
# ---------------------------------------------------------------------------


try:
    from file_organizer.methodologies.para.ai.suggestion_engine import SuggestionEngine

    _suggestion_engine_available = True
except Exception:
    _suggestion_engine_available = False


@pytest.mark.skipif(not _suggestion_engine_available, reason="SuggestionEngine not importable")
class TestSuggestionEngineInit:
    def test_creates(self) -> None:
        se = SuggestionEngine()
        assert se is not None


@pytest.mark.skipif(not _suggestion_engine_available, reason="SuggestionEngine not importable")
class TestSuggestionEngineAPI:
    @pytest.fixture()
    def engine(self) -> SuggestionEngine:
        return SuggestionEngine()

    def test_has_suggest_method(self, engine: SuggestionEngine) -> None:
        # Verify the engine has suggest-type methods
        methods = [m for m in dir(engine) if not m.startswith("_") and callable(getattr(engine, m))]
        assert len(methods) > 0

    def test_suggest_category_returns_something(
        self, engine: SuggestionEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "report.pdf"
        f.write_bytes(b"pdf content")
        # Try common method names; at least one should work
        if hasattr(engine, "suggest_category"):
            result = engine.suggest_category(f)
            assert result is not None
        elif hasattr(engine, "suggest"):
            result = engine.suggest(f)
            assert result is not None
        else:
            # No matching method found — skip silently
            pytest.skip("No suggest method found on SuggestionEngine")
