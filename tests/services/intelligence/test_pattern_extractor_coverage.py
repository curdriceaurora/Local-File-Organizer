"""Coverage tests for NamingPatternExtractor — targets uncovered branches."""

from __future__ import annotations

import pytest

from file_organizer.services.intelligence.pattern_extractor import (
    NamingPattern,
    NamingPatternExtractor,
    PatternElement,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# PatternElement / NamingPattern dataclass helpers
# ---------------------------------------------------------------------------


class TestNamingPatternMethods:
    def test_to_regex_with_variable_elements(self):
        pattern = NamingPattern(pattern_id="test")
        pattern.elements = [
            PatternElement("prefix", "doc", 0, is_variable=False),
            PatternElement("delimiter", "_", 1, is_variable=False),
            PatternElement("date", "{date}", 2, is_variable=True, pattern=r"\d{4}-\d{2}-\d{2}"),
        ]
        regex = pattern.to_regex()
        assert r"\d{4}-\d{2}-\d{2}" in regex
        assert "doc" in regex

    def test_to_template(self):
        pattern = NamingPattern(pattern_id="test")
        pattern.elements = [
            PatternElement("prefix", "doc", 0, is_variable=False),
            PatternElement("delimiter", "_", 1, is_variable=False),
            PatternElement("date", "{date}", 2, is_variable=True, pattern=r"\d+"),
        ]
        template = pattern.to_template()
        assert "{date}" in template
        assert "doc" in template


# ---------------------------------------------------------------------------
# analyze_filename
# ---------------------------------------------------------------------------


class TestAnalyzeFilename:
    def setup_method(self):
        self.extractor = NamingPatternExtractor()

    def test_basic_analysis(self):
        result = self.extractor.analyze_filename("report_2024-01-15_final.pdf")
        assert result["original"] == "report_2024-01-15_final.pdf"
        assert result["extension"] == ".pdf"
        assert result["has_numbers"] is True

    def test_no_delimiter_filename(self):
        result = self.extractor.analyze_filename("simplefile.txt")
        assert result["word_count"] >= 1

    def test_camelcase_filename(self):
        result = self.extractor.analyze_filename("myDocumentFile.txt")
        assert "camelCase" in result["delimiters"]


# ---------------------------------------------------------------------------
# extract_delimiters
# ---------------------------------------------------------------------------


class TestExtractDelimiters:
    def setup_method(self):
        self.extractor = NamingPatternExtractor()

    def test_underscore_delimiter(self):
        delims = self.extractor.extract_delimiters("foo_bar_baz")
        assert "_" in delims

    def test_hyphen_delimiter(self):
        delims = self.extractor.extract_delimiters("foo-bar-baz")
        assert "-" in delims

    def test_mixed_delimiters(self):
        delims = self.extractor.extract_delimiters("foo_bar-baz.qux")
        assert len(delims) >= 2

    def test_camelcase_detection(self):
        delims = self.extractor.extract_delimiters("camelCaseFileName")
        assert "camelCase" in delims


# ---------------------------------------------------------------------------
# detect_date_format
# ---------------------------------------------------------------------------


class TestDetectDateFormat:
    def setup_method(self):
        self.extractor = NamingPatternExtractor()

    def test_iso_date(self):
        result = self.extractor.detect_date_format("report_2024-01-15_v2")
        assert result is not None
        assert result["format"] == "YYYY-MM-DD"

    def test_underscore_date(self):
        result = self.extractor.detect_date_format("report_2024_01_15_v2")
        assert result is not None
        assert result["format"] == "YYYY_MM_DD"

    def test_no_date(self):
        result = self.extractor.detect_date_format("no_date_here")
        assert result is None


# ---------------------------------------------------------------------------
# extract_common_elements
# ---------------------------------------------------------------------------


class TestExtractCommonElements:
    def setup_method(self):
        self.extractor = NamingPatternExtractor()

    def test_empty_list(self):
        assert self.extractor.extract_common_elements([]) == []

    def test_common_prefix(self):
        files = ["report_jan.txt", "report_feb.txt", "report_mar.txt"]
        common = self.extractor.extract_common_elements(files)
        assert "report" in common

    def test_no_common(self):
        files = ["alpha.txt", "bravo.txt", "charlie.txt"]
        common = self.extractor.extract_common_elements(files)
        # No common elements expected between alpha/bravo/charlie
        assert isinstance(common, list)


# ---------------------------------------------------------------------------
# identify_structure_pattern
# ---------------------------------------------------------------------------


class TestIdentifyStructurePattern:
    def setup_method(self):
        self.extractor = NamingPatternExtractor()

    def test_empty_list(self):
        assert self.extractor.identify_structure_pattern([]) is None

    def test_pattern_with_common_prefix(self):
        files = [
            "project_report_2024-01-01.pdf",
            "project_summary_2024-02-01.pdf",
            "project_analysis_2024-03-01.pdf",
        ]
        pattern = self.extractor.identify_structure_pattern(files)
        assert pattern is not None
        assert pattern.delimiter == "_"
        assert pattern.has_date is True
        assert pattern.prefix == "project"

    def test_pattern_with_suffix(self):
        files = [
            "2024-01-01_report_final.pdf",
            "2024-02-01_summary_final.pdf",
            "2024-03-01_analysis_final.pdf",
        ]
        pattern = self.extractor.identify_structure_pattern(files)
        assert pattern is not None
        assert pattern.suffix == "final"


# ---------------------------------------------------------------------------
# suggest_naming_convention
# ---------------------------------------------------------------------------


class TestSuggestNamingConvention:
    def setup_method(self):
        self.extractor = NamingPatternExtractor()

    def test_suggest_with_all_parts(self):
        info = {
            "prefix": "doc",
            "content": "report",
            "include_date": True,
            "suffix": "final",
            "delimiter": "_",
            "case_convention": "lower",
            "extension": ".pdf",
        }
        result = self.extractor.suggest_naming_convention(info)
        assert result is not None
        assert result.endswith(".pdf")
        assert "doc" in result
        assert "final" in result

    def test_suggest_empty(self):
        result = self.extractor.suggest_naming_convention({})
        assert result is None

    def test_suggest_camel_case(self):
        info = {
            "content": "my_report",
            "delimiter": "_",
            "case_convention": "camel",
        }
        result = self.extractor.suggest_naming_convention(info)
        assert result is not None

    def test_suggest_pascal_case(self):
        info = {
            "content": "my_report",
            "delimiter": "_",
            "case_convention": "pascal",
        }
        result = self.extractor.suggest_naming_convention(info)
        assert result is not None

    def test_suggest_upper_case(self):
        info = {
            "content": "report",
            "delimiter": "_",
            "case_convention": "upper",
        }
        result = self.extractor.suggest_naming_convention(info)
        assert result == "REPORT"

    def test_suggest_title_case(self):
        info = {
            "content": "my report",
            "delimiter": "_",
            "case_convention": "title",
        }
        result = self.extractor.suggest_naming_convention(info)
        assert result is not None


# ---------------------------------------------------------------------------
# calculate_similarity
# ---------------------------------------------------------------------------


class TestCalculateSimilarity:
    def setup_method(self):
        self.extractor = NamingPatternExtractor()

    def test_identical_files(self):
        score = self.extractor.calculate_similarity("report_2024.pdf", "report_2024.pdf")
        assert score > 0.9

    def test_different_extensions(self):
        score = self.extractor.calculate_similarity("doc_2024.pdf", "doc_2024.txt")
        assert score < 1.0

    def test_no_delimiters_both(self):
        score = self.extractor.calculate_similarity("simple.txt", "other.txt")
        assert 0.0 <= score <= 1.0

    def test_one_has_date_other_not(self):
        score = self.extractor.calculate_similarity("report_2024-01-01.pdf", "report.pdf")
        assert score < 1.0

    def test_no_date_either(self):
        score = self.extractor.calculate_similarity("readme.md", "changelog.md")
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# generate_regex_pattern
# ---------------------------------------------------------------------------


class TestGenerateRegexPattern:
    def setup_method(self):
        self.extractor = NamingPatternExtractor()

    def test_generates_regex(self):
        files = ["report_2024-01-01.pdf", "report_2024-02-01.pdf"]
        regex = self.extractor.generate_regex_pattern(files)
        assert regex is not None

    def test_empty_returns_none(self):
        assert self.extractor.generate_regex_pattern([]) is None


# ---------------------------------------------------------------------------
# _detect_case_convention
# ---------------------------------------------------------------------------


class TestDetectCaseConvention:
    def setup_method(self):
        self.extractor = NamingPatternExtractor()

    def test_lower(self):
        assert self.extractor._detect_case_convention("lowercase") == "lower"

    def test_upper(self):
        assert self.extractor._detect_case_convention("UPPERCASE") == "upper"

    def test_title(self):
        assert self.extractor._detect_case_convention("Title") == "title"

    def test_camel(self):
        assert self.extractor._detect_case_convention("camelCase") == "camel"

    def test_pascal(self):
        assert self.extractor._detect_case_convention("PascalCase") == "pascal"

    def test_mixed(self):
        assert self.extractor._detect_case_convention("MiXeD_case") == "mixed"


# ---------------------------------------------------------------------------
# _split_by_delimiters
# ---------------------------------------------------------------------------


class TestSplitByDelimiters:
    def setup_method(self):
        self.extractor = NamingPatternExtractor()

    def test_no_delimiters(self):
        assert self.extractor._split_by_delimiters("text", []) == ["text"]

    def test_camelcase_only(self):
        result = self.extractor._split_by_delimiters("text", ["camelCase"])
        assert result == ["text"]

    def test_regular_split(self):
        result = self.extractor._split_by_delimiters("a_b_c", ["_"])
        assert result == ["a", "b", "c"]
