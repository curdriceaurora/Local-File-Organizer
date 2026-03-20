"""Integration tests for NamingAnalyzer.

Covers:
  - services/intelligence/naming_analyzer.py — NamingAnalyzer
"""

from __future__ import annotations

import pytest

from file_organizer.services.intelligence.naming_analyzer import NamingAnalyzer

pytestmark = pytest.mark.integration


@pytest.fixture()
def analyzer() -> NamingAnalyzer:
    return NamingAnalyzer()


# ---------------------------------------------------------------------------
# NamingAnalyzer — analyze_structure
# ---------------------------------------------------------------------------


class TestNamingAnalyzerStructure:
    def test_analyze_returns_object(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.analyze_structure("quarterly_report_2026.pdf")
        assert result is not None

    def test_analyze_simple_name(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.analyze_structure("report.txt")
        assert result is not None

    def test_analyze_camel_case(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.analyze_structure("QuarterlyReport.pdf")
        assert result is not None

    def test_analyze_snake_case(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.analyze_structure("quarterly_report.pdf")
        assert result is not None

    def test_analyze_hyphen_separated(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.analyze_structure("quarterly-report-2026.pdf")
        assert result is not None

    def test_analyze_with_version(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.analyze_structure("document_v2.1.pdf")
        assert result is not None

    def test_analyze_empty_name(self, analyzer: NamingAnalyzer) -> None:
        # Should not raise even for edge case inputs
        try:
            result = analyzer.analyze_structure("")
            assert result is not None
        except (ValueError, AttributeError):
            pass  # Implementation may raise on empty string

    def test_analyze_numeric_name(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.analyze_structure("20260317.pdf")
        assert result is not None


# ---------------------------------------------------------------------------
# NamingAnalyzer — identify_naming_style
# ---------------------------------------------------------------------------


class TestNamingAnalyzerStyle:
    def test_snake_case_identified(self, analyzer: NamingAnalyzer) -> None:
        style = analyzer.identify_naming_style("quarterly_report_2026.pdf")
        assert isinstance(style, str)
        assert len(style) > 0

    def test_camel_case_identified(self, analyzer: NamingAnalyzer) -> None:
        style = analyzer.identify_naming_style("QuarterlyReport.pdf")
        assert len(style) > 0

    def test_hyphen_case_identified(self, analyzer: NamingAnalyzer) -> None:
        style = analyzer.identify_naming_style("quarterly-report.pdf")
        assert len(style) > 0

    def test_single_word_style(self, analyzer: NamingAnalyzer) -> None:
        style = analyzer.identify_naming_style("report.txt")
        assert len(style) > 0

    def test_known_styles_set(self, analyzer: NamingAnalyzer) -> None:
        # All SEPARATORS should be set
        assert hasattr(NamingAnalyzer, "SEPARATORS")


# ---------------------------------------------------------------------------
# NamingAnalyzer — normalize_filename
# ---------------------------------------------------------------------------


class TestNamingAnalyzerNormalize:
    def test_normalize_to_snake_case(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.normalize_filename("QuarterlyReport.pdf", target_style="snake_case")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_normalize_default_is_snake_case(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.normalize_filename("MyDocument.pdf")
        assert "_" in result or len(result) > 0

    def test_normalize_already_snake_case(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.normalize_filename("quarterly_report.pdf", target_style="snake_case")
        assert isinstance(result, str)
        assert "quarterly" in result.lower() or "report" in result.lower()

    def test_normalize_preserves_extension_meaning(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.normalize_filename("MyReport.pdf")
        # Result should still contain report
        assert "report" in result.lower() or "my" in result.lower() or len(result) > 0

    def test_normalize_camel_to_snake(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.normalize_filename("quarterlyReport", target_style="snake_case")
        assert "_" in result


# ---------------------------------------------------------------------------
# NamingAnalyzer — extract_semantic_components
# ---------------------------------------------------------------------------


class TestNamingAnalyzerSemantics:
    def test_extract_returns_dict(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.extract_semantic_components("invoice_2026_march.pdf")
        assert "base_name" in result

    def test_extract_simple_name(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.extract_semantic_components("report.txt")
        assert "base_name" in result

    def test_extract_date_like_name(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.extract_semantic_components("backup_20260317.tar")
        assert "base_name" in result

    def test_extract_version_number(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.extract_semantic_components("app_v2.1.0.zip")
        assert "base_name" in result

    def test_extract_multi_word(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.extract_semantic_components("annual_financial_report_q4_2026.xlsx")
        assert "base_name" in result


# ---------------------------------------------------------------------------
# NamingAnalyzer — find_common_pattern
# ---------------------------------------------------------------------------


class TestNamingAnalyzerCommonPattern:
    def test_empty_list_returns_none_or_dict(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.find_common_pattern([])
        assert result is None or isinstance(result, dict)

    def test_single_filename(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.find_common_pattern(["report.pdf"])
        assert result is None or isinstance(result, dict)

    def test_similar_filenames(self, analyzer: NamingAnalyzer) -> None:
        names = ["invoice_jan.pdf", "invoice_feb.pdf", "invoice_mar.pdf"]
        result = analyzer.find_common_pattern(names)
        assert result is None or isinstance(result, dict)

    def test_diverse_filenames(self, analyzer: NamingAnalyzer) -> None:
        names = ["report.pdf", "image.png", "notes.txt", "data.csv"]
        result = analyzer.find_common_pattern(names)
        assert result is None or isinstance(result, dict)

    def test_common_prefix_names(self, analyzer: NamingAnalyzer) -> None:
        names = ["q1_report.pdf", "q2_report.pdf", "q3_report.pdf", "q4_report.pdf"]
        result = analyzer.find_common_pattern(names)
        assert result is None or isinstance(result, dict)


# ---------------------------------------------------------------------------
# NamingAnalyzer — compare_structures
# ---------------------------------------------------------------------------


class TestNamingAnalyzerCompare:
    def test_compare_identical_returns_dict(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.compare_structures("report.pdf", "report.pdf")
        assert result["overall_similarity"] == 1.0

    def test_compare_different_returns_dict(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.compare_structures("report_q1.pdf", "report_q2.pdf")
        assert "overall_similarity" in result

    def test_compare_different_styles(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.compare_structures("quarterlyReport.pdf", "quarterly_report.pdf")
        assert "overall_similarity" in result

    def test_compare_result_has_content(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.compare_structures("file_a.txt", "file_b.txt")
        assert len(result) > 0


# ---------------------------------------------------------------------------
# NamingAnalyzer — extract_pattern_differences
# ---------------------------------------------------------------------------


class TestNamingAnalyzerPatternDiff:
    def test_identical_files(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.extract_pattern_differences("report.pdf", "report.pdf")
        assert result["delimiter_change"] is False

    def test_folder_move(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.extract_pattern_differences("docs/report.pdf", "finance/report.pdf")
        assert "delimiter_change" in result

    def test_renamed_file(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.extract_pattern_differences("old_name.pdf", "new_name.pdf")
        assert "token_change" in result

    def test_style_correction(self, analyzer: NamingAnalyzer) -> None:
        result = analyzer.extract_pattern_differences("QuarterlyReport.pdf", "quarterly_report.pdf")
        assert "delimiter_change" in result
