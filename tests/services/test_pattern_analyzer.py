"""
Unit tests for Pattern Analyzer service.

Tests pattern detection, naming convention analysis, location-based patterns,
content clustering, and directory structure analysis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from file_organizer.services.pattern_analyzer import (
    ContentCluster,
    LocationPattern,
    NamingPattern,
    PatternAnalysis,
    PatternAnalyzer,
)


@pytest.mark.unit
class TestNamingPattern:
    """Tests for NamingPattern dataclass."""

    def test_create_naming_pattern(self):
        """Test creating a naming pattern."""
        pattern = NamingPattern(
            pattern="DATE_PREFIX",
            regex=r"^([0-9]{4}[-_][0-9]{2}[-_][0-9]{2})_",
            example_files=["2024-01-15_file.txt", "2024-02-20_report.pdf"],
            count=42,
            confidence=0.85,
            description="Date prefix pattern (YYYY-MM-DD)",
        )

        assert pattern.pattern == "DATE_PREFIX"
        assert pattern.count == 42
        assert pattern.confidence == 0.85
        assert len(pattern.example_files) == 2


@pytest.mark.unit
class TestLocationPattern:
    """Tests for LocationPattern dataclass."""

    def test_create_location_pattern(self):
        """Test creating a location pattern."""
        pattern = LocationPattern(
            directory=Path("/documents"),
            file_types={".pdf", ".docx"},
            naming_patterns=["DATE_PREFIX"],
            file_count=15,
            depth_level=2,
            category="documents",
        )

        assert pattern.directory == Path("/documents")
        assert ".pdf" in pattern.file_types
        assert pattern.file_count == 15


@pytest.mark.unit
class TestContentCluster:
    """Tests for ContentCluster dataclass."""

    def test_create_content_cluster(self):
        """Test creating a content cluster."""
        cluster = ContentCluster(
            cluster_id="cluster_001",
            file_paths=[Path("/file1.txt"), Path("/file2.txt")],
            common_keywords=["report", "financial"],
            file_types={".txt", ".pdf"},
            size_range=(1000, 50000),
            category="financial_reports",
            confidence=0.78,
        )

        assert cluster.cluster_id == "cluster_001"
        assert len(cluster.file_paths) == 2
        assert cluster.confidence == 0.78


@pytest.mark.unit
class TestPatternAnalysisDataclass:
    """Tests for PatternAnalysis dataclass."""

    def test_create_pattern_analysis(self):
        """Test creating pattern analysis result."""
        analysis = PatternAnalysis(
            directory=Path("/test"),
            naming_patterns=[],
            location_patterns=[],
            content_clusters=[],
            file_type_distribution={".txt": 10, ".pdf": 5},
            depth_distribution={1: 8, 2: 7},
            analyzed_at=datetime.now(UTC),
            total_files=15,
        )

        assert analysis.directory == Path("/test")
        assert analysis.total_files == 15
        assert analysis.file_type_distribution[".txt"] == 10


@pytest.mark.unit
class TestPatternAnalyzerInit:
    """Tests for PatternAnalyzer initialization."""

    def test_init_default_parameters(self):
        """Test initialization with default parameters."""
        analyzer = PatternAnalyzer()

        assert analyzer.min_pattern_count == 3
        assert analyzer.max_depth == 10
        assert len(analyzer.common_patterns) > 0

    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        analyzer = PatternAnalyzer(min_pattern_count=5, max_depth=5)

        assert analyzer.min_pattern_count == 5
        assert analyzer.max_depth == 5

    def test_has_common_patterns(self):
        """Test that analyzer has common patterns defined."""
        analyzer = PatternAnalyzer()

        pattern_types = [t for _, t in analyzer.common_patterns]
        assert "DATE_PREFIX" in pattern_types
        assert "VERSION" in pattern_types
        assert "SNAKE_CASE" in pattern_types


@pytest.mark.unit
class TestAnalyzeDirectory:
    """Tests for analyzing directories."""

    def test_analyze_empty_directory(self):
        """Test analyzing an empty directory."""
        with TemporaryDirectory() as tmpdir:
            analyzer = PatternAnalyzer()
            analysis = analyzer.analyze_directory(Path(tmpdir))

            assert analysis.total_files == 0
            assert len(analysis.naming_patterns) == 0
            assert isinstance(analysis, PatternAnalysis)

    def test_analyze_directory_with_files(self):
        """Test analyzing directory with files."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            for i in range(3):
                (tmppath / f"file{i}.txt").write_text(f"content {i}")

            analyzer = PatternAnalyzer()
            analysis = analyzer.analyze_directory(tmppath)

            assert analysis.total_files == 3
            assert len(analysis.file_type_distribution) > 0

    def test_analyze_invalid_directory(self):
        """Test analyzing non-existent directory raises error."""
        analyzer = PatternAnalyzer()

        with pytest.raises(ValueError):
            analyzer.analyze_directory(Path("/nonexistent/path"))

    def test_analyze_file_instead_of_directory(self):
        """Test analyzing a file instead of directory raises error."""
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "file.txt"
            file_path.write_text("content")

            analyzer = PatternAnalyzer()

            with pytest.raises(ValueError):
                analyzer.analyze_directory(file_path)

    def test_analyze_respects_max_depth(self):
        """Test that analysis respects max_depth parameter."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create nested structure
            (tmppath / "level1").mkdir()
            (tmppath / "level1" / "level2").mkdir()
            (tmppath / "level1" / "level2" / "level3").mkdir()

            # Create files at different levels
            (tmppath / "root.txt").write_text("root")
            (tmppath / "level1" / "l1.txt").write_text("level1")
            (tmppath / "level1" / "level2" / "l2.txt").write_text("level2")
            (tmppath / "level1" / "level2" / "level3" / "l3.txt").write_text("level3")

            analyzer = PatternAnalyzer(max_depth=2)
            analysis = analyzer.analyze_directory(tmppath)

            # Should find exactly 3 files up to depth 2, but not deeper (skips l3.txt at depth 3)
            assert analysis.total_files == 3


@pytest.mark.unit
class TestFileCollection:
    """Tests for file collection."""

    def test_collect_files_single_level(self):
        """Test collecting files from single directory level."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            for i in range(5):
                (tmppath / f"file{i}.txt").write_text(f"content {i}")

            analyzer = PatternAnalyzer()
            files = analyzer._collect_files(tmppath)

            assert len(files) == 5

    def test_collect_files_recursive(self):
        """Test recursive file collection."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "subdir").mkdir()

            (tmppath / "root.txt").write_text("root")
            (tmppath / "subdir" / "nested.txt").write_text("nested")

            analyzer = PatternAnalyzer()
            files = analyzer._collect_files(tmppath)

            assert len(files) == 2
            assert any(f.name == "root.txt" for f in files)
            assert any(f.name == "nested.txt" for f in files)

    def test_collect_files_ignores_hidden_directories(self):
        """Test that hidden directories are ignored."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / ".hidden").mkdir()

            (tmppath / "visible.txt").write_text("visible")
            (tmppath / ".hidden" / "hidden.txt").write_text("hidden")

            analyzer = PatternAnalyzer()
            files = analyzer._collect_files(tmppath)

            assert len(files) == 1
            assert files[0].name == "visible.txt"

    def test_collect_respects_depth_limit(self):
        """Test that collection respects depth limit."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            current = tmppath
            for i in range(5):
                current = current / f"level{i}"
                current.mkdir()
                (current / f"file{i}.txt").write_text(f"content {i}")

            analyzer = PatternAnalyzer(max_depth=2)
            files = analyzer._collect_files(tmppath)

            # Should find files only up to depth 2
            assert len(files) <= 3


@pytest.mark.unit
class TestNamingPatternDetection:
    """Tests for naming pattern detection."""

    def test_detect_date_prefix_pattern(self):
        """Test detecting date prefix naming pattern."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create files with date prefix
            for i in range(3):
                (tmppath / f"2024-01-{15 + i:02d}_report.pdf").write_text("content")

            analyzer = PatternAnalyzer(min_pattern_count=3)
            files = analyzer._collect_files(tmppath)
            patterns = analyzer.detect_naming_patterns(files)

            # Should detect date prefix pattern
            pattern_types = [p.pattern for p in patterns]
            assert "DATE_PREFIX" in pattern_types

    def test_detect_snake_case_pattern(self):
        """Test detecting snake_case naming pattern."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create files with snake_case names
            for name in [
                "report_q1_2024.txt",
                "summary_sales_data.txt",
                "invoice_monthly_2024.txt",
            ]:
                (tmppath / name).write_text("content")

            analyzer = PatternAnalyzer(min_pattern_count=3)
            files = analyzer._collect_files(tmppath)
            patterns = analyzer.detect_naming_patterns(files)

            pattern_types = [p.pattern for p in patterns]
            assert "SNAKE_CASE" in pattern_types

    def test_pattern_confidence_calculation(self):
        """Test that pattern confidence is calculated correctly."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create 5 files with date prefix, 5 without
            for i in range(5):
                (tmppath / f"2024-01-{15 + i:02d}_file.txt").write_text("content")
            for i in range(5):
                (tmppath / f"random_file_{i}.txt").write_text("content")

            analyzer = PatternAnalyzer(min_pattern_count=3)
            files = analyzer._collect_files(tmppath)
            patterns = analyzer.detect_naming_patterns(files)

            date_pattern = next((p for p in patterns if p.pattern == "DATE_PREFIX"), None)
            assert date_pattern is not None
            # 5 files with pattern out of 10 = 50% confidence
            assert date_pattern.confidence == 50.0

    def test_minimum_pattern_count_threshold(self):
        """Test that patterns below min_pattern_count are excluded."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create only 2 files with version pattern
            (tmppath / "app_v1.0.txt").write_text("content")
            (tmppath / "tool_v2.1.txt").write_text("content")
            # Add 5 random files
            for i in range(5):
                (tmppath / f"random_{i}.txt").write_text("content")

            analyzer = PatternAnalyzer(min_pattern_count=3)
            files = analyzer._collect_files(tmppath)
            patterns = analyzer.detect_naming_patterns(files)

            version_patterns = [p for p in patterns if p.pattern == "VERSION"]
            # Should be excluded because count < min_pattern_count
            assert len(version_patterns) == 0


@pytest.mark.unit
class TestFileTypeAnalysis:
    """Tests for file type analysis."""

    def test_analyze_file_types(self):
        """Test file type distribution analysis."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "doc1.txt").write_text("text")
            (tmppath / "doc2.txt").write_text("text")
            (tmppath / "image.jpg").write_text("image")
            (tmppath / "report.pdf").write_text("pdf")

            analyzer = PatternAnalyzer()
            files = analyzer._collect_files(tmppath)
            file_type_dist = analyzer._analyze_file_types(files)

            assert file_type_dist[".txt"] == 2
            assert file_type_dist[".jpg"] == 1
            assert file_type_dist[".pdf"] == 1

    def test_file_type_distribution_in_analysis(self):
        """Test that file type distribution is included in analysis."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "file1.txt").write_text("text1")
            (tmppath / "file2.txt").write_text("text2")
            (tmppath / "file3.pdf").write_text("pdf")

            analyzer = PatternAnalyzer()
            analysis = analyzer.analyze_directory(tmppath)

            assert ".txt" in analysis.file_type_distribution
            assert ".pdf" in analysis.file_type_distribution
            assert analysis.file_type_distribution[".txt"] == 2


@pytest.mark.unit
class TestDepthAnalysis:
    """Tests for directory depth analysis."""

    def test_analyze_depth_distribution(self):
        """Test analyzing directory depth distribution."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create files at different depths
            (tmppath / "root.txt").write_text("root")

            (tmppath / "level1").mkdir()
            (tmppath / "level1" / "l1_file.txt").write_text("level1")

            (tmppath / "level1" / "level2").mkdir()
            (tmppath / "level1" / "level2" / "l2_file.txt").write_text("level2")

            analyzer = PatternAnalyzer()
            files = analyzer._collect_files(tmppath)
            depth_dist = analyzer._analyze_depth_distribution(files, tmppath)

            assert isinstance(depth_dist, dict)
            assert len(depth_dist) >= 2  # At least 2 different depths


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases."""

    def test_directory_with_special_characters(self):
        """Test analyzing directory with special characters in name."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir) / "dir_with-special.chars"
            tmppath.mkdir()

            (tmppath / "file.txt").write_text("content")

            analyzer = PatternAnalyzer()
            analysis = analyzer.analyze_directory(tmppath)

            assert analysis.total_files == 1

    def test_files_with_no_extension(self):
        """Test handling files without extensions."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "README").write_text("readme")
            (tmppath / "Makefile").write_text("makefile")

            analyzer = PatternAnalyzer()
            files = analyzer._collect_files(tmppath)

            assert len(files) == 2

    def test_files_with_multiple_dots(self):
        """Test handling files with multiple dots."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "archive.tar.gz").write_text("archive")
            (tmppath / "data.backup.sql").write_text("data")

            analyzer = PatternAnalyzer()
            files = analyzer._collect_files(tmppath)

            assert len(files) == 2

    def test_very_long_filename(self):
        """Test handling very long filenames."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            long_name = "x" * 200 + ".txt"
            (tmppath / long_name).write_text("content")

            analyzer = PatternAnalyzer()
            analysis = analyzer.analyze_directory(tmppath)

            assert analysis.total_files == 1

    def test_unicode_filenames(self):
        """Test handling unicode characters in filenames."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "файл_ファイル_文件.txt").write_text("unicode content")

            analyzer = PatternAnalyzer()
            analysis = analyzer.analyze_directory(tmppath)

            assert analysis.total_files == 1
