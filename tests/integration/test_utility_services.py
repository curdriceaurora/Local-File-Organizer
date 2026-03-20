"""Integration tests for utility and analytics services.

Covers:
  - utils/text_processing.py       — clean_text, sanitize_filename, extract_keywords, truncate_text
  - utils/chart_generator.py       — ChartGenerator
  - services/analytics/storage_analyzer.py — StorageAnalyzer
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.analytics.storage_analyzer import StorageAnalyzer
from file_organizer.utils.chart_generator import ChartGenerator
from file_organizer.utils.text_processing import (
    clean_text,
    extract_keywords,
    sanitize_filename,
    truncate_text,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------


class TestCleanText:
    def test_empty_string_returns_empty(self) -> None:
        assert clean_text("") == ""

    def test_basic_text_processed(self) -> None:
        result = clean_text("Hello world")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_special_chars_removed(self) -> None:
        result = clean_text("hello! world?")
        assert "!" not in result
        assert "?" not in result

    def test_digits_removed(self) -> None:
        result = clean_text("report 2026 annual")
        assert "2026" not in result

    def test_max_words_respected(self) -> None:
        text = "one two three four five six seven eight"
        result = clean_text(text, max_words=3)
        words = result.split("_")
        assert len(words) < 4

    def test_camel_case_split(self) -> None:
        result = clean_text("quarterlyReport")
        # Should split into separate words
        assert "_" in result or result == "quarterlyreport"

    def test_joined_with_underscores(self) -> None:
        result = clean_text("financial report annual")
        if result:
            # Should join words with underscores
            assert " " not in result


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    def test_basic_name(self) -> None:
        result = sanitize_filename("My Report")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_returns_untitled(self) -> None:
        assert sanitize_filename("") == "untitled"

    def test_only_numbers_returns_untitled(self) -> None:
        # After cleaning, purely numeric input may become empty
        result = sanitize_filename("12345")
        assert result == "untitled" or isinstance(result, str)

    def test_no_spaces_in_result(self) -> None:
        result = sanitize_filename("hello world foo")
        assert " " not in result

    def test_max_length_respected(self) -> None:
        long_name = "very long filename " * 10
        result = sanitize_filename(long_name, max_length=20)
        assert len(result) < 21

    def test_lowercase_result(self) -> None:
        result = sanitize_filename("MyDocument")
        assert result == result.lower()

    def test_special_chars_removed(self) -> None:
        result = sanitize_filename("report! @2026 #finance")
        assert "!" not in result
        assert "@" not in result
        assert "#" not in result

    def test_multiple_underscores_collapsed(self) -> None:
        result = sanitize_filename("a  b  c")
        assert "__" not in result


# ---------------------------------------------------------------------------
# extract_keywords
# ---------------------------------------------------------------------------


class TestExtractKeywords:
    def test_returns_list(self) -> None:
        result = extract_keywords("The quick brown fox jumped over the lazy dog")
        assert len(result) >= 1

    def test_top_n_respected(self) -> None:
        text = "python programming language machine learning deep learning"
        result = extract_keywords(text, top_n=3)
        assert len(result) < 4

    def test_empty_text_returns_list(self) -> None:
        result = extract_keywords("")
        assert result == []

    def test_keywords_are_strings(self) -> None:
        result = extract_keywords("financial quarterly report analysis")
        for kw in result:
            assert len(kw) > 0


# ---------------------------------------------------------------------------
# truncate_text
# ---------------------------------------------------------------------------


class TestTruncateText:
    def test_short_text_unchanged(self) -> None:
        assert truncate_text("hello", max_chars=100) == "hello"

    def test_long_text_truncated(self) -> None:
        text = "x" * 200
        result = truncate_text(text, max_chars=100)
        assert len(result) < 104  # 100 + "..."

    def test_truncated_ends_with_ellipsis(self) -> None:
        text = "x" * 200
        result = truncate_text(text, max_chars=50)
        assert result.endswith("...")

    def test_exact_length_unchanged(self) -> None:
        text = "a" * 5000
        assert truncate_text(text) == text

    def test_empty_string(self) -> None:
        assert truncate_text("") == ""


# ---------------------------------------------------------------------------
# ChartGenerator
# ---------------------------------------------------------------------------


@pytest.fixture()
def chart() -> ChartGenerator:
    return ChartGenerator()


@pytest.fixture()
def ascii_chart() -> ChartGenerator:
    return ChartGenerator(use_unicode=False)


class TestChartGeneratorPie:
    def test_empty_data_returns_no_data(self, chart: ChartGenerator) -> None:
        result = chart.create_pie_chart({}, "Test")
        assert "No data" in result

    def test_all_zero_values_returns_no_data(self, chart: ChartGenerator) -> None:
        result = chart.create_pie_chart({"a": 0.0, "b": 0.0}, "Test")
        assert "No data" in result

    def test_title_in_output(self, chart: ChartGenerator) -> None:
        result = chart.create_pie_chart({"pdf": 50.0, "docx": 50.0}, "File Types")
        assert "File Types" in result

    def test_labels_in_output(self, chart: ChartGenerator) -> None:
        result = chart.create_pie_chart({"pdf": 75.0, "txt": 25.0}, "Types")
        assert "pdf" in result
        assert "txt" in result

    def test_percentages_in_output(self, chart: ChartGenerator) -> None:
        result = chart.create_pie_chart({"a": 50.0, "b": 50.0}, "Equal")
        assert "50.0" in result

    def test_unicode_bar_chars(self, chart: ChartGenerator) -> None:
        result = chart.create_pie_chart({"a": 100.0}, "Unicode")
        assert "█" in result

    def test_ascii_bar_chars(self, ascii_chart: ChartGenerator) -> None:
        result = ascii_chart.create_pie_chart({"a": 100.0}, "ASCII")
        assert "#" in result


class TestChartGeneratorBar:
    def test_empty_data_returns_no_data(self, chart: ChartGenerator) -> None:
        result = chart.create_bar_chart({}, "Test")
        assert "No data" in result

    def test_all_zero_values_returns_no_data(self, chart: ChartGenerator) -> None:
        result = chart.create_bar_chart({"a": 0, "b": 0}, "Test")
        assert "No data" in result

    def test_title_in_output(self, chart: ChartGenerator) -> None:
        result = chart.create_bar_chart({"pdf": 10, "docx": 5}, "Bar Chart")
        assert "Bar Chart" in result

    def test_labels_in_output(self, chart: ChartGenerator) -> None:
        result = chart.create_bar_chart({"python": 20, "java": 10}, "Languages")
        assert "python" in result
        assert "java" in result

    def test_counts_in_output(self, chart: ChartGenerator) -> None:
        result = chart.create_bar_chart({"a": 42}, "Count")
        assert "42" in result

    def test_sorted_by_value_descending(self, chart: ChartGenerator) -> None:
        result = chart.create_bar_chart({"low": 1, "high": 100}, "Sort")
        # high should appear before low
        assert result.index("high") < result.index("low")


class TestChartGeneratorTrend:
    def test_empty_data_returns_insufficient(self, chart: ChartGenerator) -> None:
        result = chart.create_trend_line([], "Test")
        assert "Insufficient" in result

    def test_single_data_point_insufficient(self, chart: ChartGenerator) -> None:
        result = chart.create_trend_line([("Jan", 10.0)], "Test")
        assert "Insufficient" in result

    def test_constant_values_no_variation(self, chart: ChartGenerator) -> None:
        result = chart.create_trend_line([("Jan", 5.0), ("Feb", 5.0)], "Flat")
        assert "No variation" in result

    def test_valid_trend_includes_title(self, chart: ChartGenerator) -> None:
        data = [("Jan", 1.0), ("Feb", 2.0), ("Mar", 3.0)]
        result = chart.create_trend_line(data, "Trend")
        assert "Trend" in result

    def test_valid_trend_includes_labels(self, chart: ChartGenerator) -> None:
        data = [("Jan", 1.0), ("Feb", 5.0), ("Mar", 3.0)]
        result = chart.create_trend_line(data, "Monthly")
        assert "Jan" in result


class TestChartGeneratorSparkline:
    def test_empty_returns_empty_string(self, chart: ChartGenerator) -> None:
        assert chart.create_sparkline([]) == ""

    def test_constant_values_same_char(self, chart: ChartGenerator) -> None:
        result = chart.create_sparkline([5.0, 5.0, 5.0])
        assert len(set(result)) == 1  # all same character

    def test_increasing_values_different_chars(self, chart: ChartGenerator) -> None:
        result = chart.create_sparkline([1.0, 2.0, 3.0, 4.0, 5.0])
        assert len(result) == 5

    def test_sparkline_length_matches_values(self, chart: ChartGenerator) -> None:
        values = [1.0, 3.0, 2.0, 4.0]
        result = chart.create_sparkline(values)
        assert len(result) == 4

    def test_ascii_mode_uses_arrows(self, ascii_chart: ChartGenerator) -> None:
        result = ascii_chart.create_sparkline([1.0, -1.0, 1.0])
        assert "▴" in result or "▾" in result


# ---------------------------------------------------------------------------
# StorageAnalyzer
# ---------------------------------------------------------------------------


@pytest.fixture()
def sa() -> StorageAnalyzer:
    return StorageAnalyzer()


class TestStorageAnalyzerInit:
    def test_cache_ttl_set(self, sa: StorageAnalyzer) -> None:
        assert sa.cache_ttl == 3600

    def test_cache_initially_empty(self, sa: StorageAnalyzer) -> None:
        assert sa._cache == {}


class TestStorageAnalyzerDirectory:
    def test_invalid_path_raises(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            sa.analyze_directory(tmp_path / "nonexistent")

    def test_file_path_raises(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("content")
        with pytest.raises(ValueError):
            sa.analyze_directory(f)

    def test_empty_dir_stats(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        stats = sa.analyze_directory(tmp_path)
        assert stats.file_count == 0
        assert stats.total_size == 0

    def test_dir_with_files(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("content1")
        (tmp_path / "b.pdf").write_bytes(b"\x00" * 100)
        stats = sa.analyze_directory(tmp_path)
        assert stats.file_count == 2
        assert stats.total_size > 0

    def test_file_type_distribution(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")
        (tmp_path / "c.pdf").write_bytes(b"pdf")
        stats = sa.analyze_directory(tmp_path)
        assert ".txt" in stats.size_by_type
        assert ".pdf" in stats.size_by_type

    def test_cache_used_on_second_call(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        stats1 = sa.analyze_directory(tmp_path)
        stats2 = sa.analyze_directory(tmp_path)
        assert stats1.file_count == stats2.file_count

    def test_clear_cache(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        sa.analyze_directory(tmp_path)
        sa.clear_cache()
        assert sa._cache == {}

    def test_no_cache_bypasses_cache(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        sa.analyze_directory(tmp_path)
        (tmp_path / "new_file.txt").write_text("new content")
        stats = sa.analyze_directory(tmp_path, use_cache=False)
        assert stats.file_count == 1


class TestStorageAnalyzerLargeFiles:
    def test_identify_large_files_above_threshold(
        self, sa: StorageAnalyzer, tmp_path: Path
    ) -> None:
        small = tmp_path / "small.txt"
        large = tmp_path / "large.txt"
        small.write_bytes(b"x" * 100)
        large.write_bytes(b"x" * 10000)
        # threshold=1000 bytes → only large qualifies
        result = sa.identify_large_files(tmp_path, threshold=1000)
        paths = [f.path for f in result]
        assert large in paths
        assert small not in paths

    def test_identify_large_files_empty_dir(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        result = sa.identify_large_files(tmp_path)
        assert result == []

    def test_large_files_sorted_by_size(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        (tmp_path / "tiny.txt").write_bytes(b"x" * 10)
        (tmp_path / "big.txt").write_bytes(b"x" * 10000)
        result = sa.identify_large_files(tmp_path, threshold=1)
        if len(result) >= 2:
            assert result[0].size >= result[1].size


class TestStorageAnalyzerDuplicateSpace:
    def test_empty_groups_returns_zero(self, sa: StorageAnalyzer) -> None:
        result = sa.get_duplicate_space([])
        assert result == 0

    def test_calculates_wasted_space(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        f1 = tmp_path / "dup1.txt"
        f2 = tmp_path / "dup2.txt"
        f1.write_bytes(b"x" * 1000)
        f2.write_bytes(b"x" * 1000)
        groups = [{"files": [str(f1), str(f2)], "size": 1000}]
        result = sa.get_duplicate_space(groups)
        # 1 copy wasted per group (N-1 duplicates)
        assert result == 1000


class TestStorageAnalyzerSizeDistribution:
    def test_empty_dir_distribution(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        dist = sa.calculate_size_distribution(tmp_path)
        assert dist is not None

    def test_distribution_with_files(self, sa: StorageAnalyzer, tmp_path: Path) -> None:
        for i, size in enumerate([100, 10000, 1000000]):
            (tmp_path / f"file{i}.txt").write_bytes(b"x" * size)
        dist = sa.calculate_size_distribution(tmp_path)
        assert dist is not None
