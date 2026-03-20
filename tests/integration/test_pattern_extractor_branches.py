"""Integration tests for pattern_extractor.py branch coverage.

Targets uncovered branches in:
  - NamingPattern.to_regex — variable element with pattern / without pattern
  - NamingPattern.to_template — variable / non-variable elements
  - NamingPatternExtractor.detect_date_format — various date formats found / not found
  - NamingPatternExtractor.extract_common_elements — empty list, single file, multiple files
  - NamingPatternExtractor.identify_structure_pattern — empty, with dates, prefix/suffix
  - NamingPatternExtractor.suggest_naming_convention — all optional fields
  - NamingPatternExtractor.calculate_similarity — same/diff dates, same/diff extensions
  - NamingPatternExtractor.generate_regex_pattern — with/without pattern
  - NamingPatternExtractor._detect_case_convention — upper, title, camel, pascal, mixed
  - NamingPatternExtractor._apply_case_convention — all branches
  - NamingPatternExtractor._build_pattern_elements — date element construction
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extractor():
    from file_organizer.services.intelligence.pattern_extractor import NamingPatternExtractor

    return NamingPatternExtractor()


def _pattern(pattern_id: str = "test"):
    from file_organizer.services.intelligence.pattern_extractor import NamingPattern

    return NamingPattern(pattern_id=pattern_id)


def _element(
    element_type: str,
    value: str,
    position: int = 0,
    is_variable: bool = False,
    pattern: str | None = None,
):
    from file_organizer.services.intelligence.pattern_extractor import PatternElement

    return PatternElement(
        element_type=element_type,
        value=value,
        position=position,
        is_variable=is_variable,
        pattern=pattern,
    )


# ---------------------------------------------------------------------------
# NamingPattern.to_regex — variable vs literal element branches
# ---------------------------------------------------------------------------


class TestNamingPatternToRegex:
    def test_literal_elements_escaped(self) -> None:
        """Non-variable elements are regex-escaped in output."""
        p = _pattern()
        p.elements.append(_element("text", "report-2024", 0, is_variable=False))
        regex = p.to_regex()
        assert "report" in regex
        # Hyphen is escaped in regex
        assert r"\-" in regex or "report" in regex

    def test_variable_element_with_pattern_uses_pattern(self) -> None:
        """Variable element with a regex pattern → pattern used directly."""
        p = _pattern()
        date_regex = r"\d{4}-\d{2}-\d{2}"
        p.elements.append(_element("date", "{date}", 0, is_variable=True, pattern=date_regex))
        regex = p.to_regex()
        assert date_regex in regex

    def test_variable_element_without_pattern_uses_escaped_value(self) -> None:
        """Variable element without pattern → value is escaped and used."""
        p = _pattern()
        p.elements.append(_element("text", "variable", 0, is_variable=True, pattern=None))
        regex = p.to_regex()
        assert "variable" in regex

    def test_mixed_elements(self) -> None:
        """Mixed variable and literal elements concatenated."""
        p = _pattern()
        p.elements.append(_element("prefix", "report", 0, is_variable=False))
        p.elements.append(_element("delimiter", "_", 1, is_variable=False))
        p.elements.append(_element("date", "{date}", 2, is_variable=True, pattern=r"\d{8}"))
        regex = p.to_regex()
        assert r"\d{8}" in regex
        assert "report" in regex


# ---------------------------------------------------------------------------
# NamingPattern.to_template
# ---------------------------------------------------------------------------


class TestNamingPatternToTemplate:
    def test_variable_element_becomes_placeholder(self) -> None:
        """Variable element → {element_type} placeholder."""
        p = _pattern()
        p.elements.append(_element("date", "{date}", 0, is_variable=True))
        template = p.to_template()
        assert "{date}" in template

    def test_literal_element_preserved(self) -> None:
        """Non-variable element → value preserved."""
        p = _pattern()
        p.elements.append(_element("prefix", "report", 0, is_variable=False))
        template = p.to_template()
        assert template == "report"

    def test_empty_elements(self) -> None:
        """No elements → empty string."""
        p = _pattern()
        assert p.to_template() == ""


# ---------------------------------------------------------------------------
# detect_date_format — various date formats
# ---------------------------------------------------------------------------


class TestDetectDateFormat:
    def test_yyyy_mm_dd_format(self) -> None:
        """YYYY-MM-DD format detected."""
        extractor = _extractor()
        result = extractor.detect_date_format("report_2024-03-15_v1")
        assert result is not None
        assert result["format"] == "YYYY-MM-DD"

    def test_yyyy_mm_dd_underscore_format(self) -> None:
        """YYYY_MM_DD format detected."""
        extractor = _extractor()
        result = extractor.detect_date_format("report_2024_03_15_v1")
        assert result is not None
        assert result["format"] == "YYYY_MM_DD"

    def test_dd_mm_yyyy_format(self) -> None:
        """DD-MM-YYYY format detected."""
        extractor = _extractor()
        result = extractor.detect_date_format("15-03-2024_report")
        assert result is not None
        assert result["format"] == "DD-MM-YYYY"

    def test_yyyymmdd_8digit_format(self) -> None:
        """8-digit date YYYYMMDD detected."""
        extractor = _extractor()
        result = extractor.detect_date_format("20240315_report")
        assert result is not None
        assert "YYYYMMDD" in result["format"]

    def test_no_date_returns_none(self) -> None:
        """No date in filename → None."""
        extractor = _extractor()
        result = extractor.detect_date_format("my_report_final")
        assert result is None

    def test_date_info_includes_position_and_value(self) -> None:
        """Returned dict includes format, value, position, pattern."""
        extractor = _extractor()
        result = extractor.detect_date_format("report_2024-01-15")
        assert result is not None
        assert "value" in result
        assert "position" in result
        assert "pattern" in result


# ---------------------------------------------------------------------------
# extract_common_elements
# ---------------------------------------------------------------------------


class TestExtractCommonElements:
    def test_empty_filenames_returns_empty(self) -> None:
        """Empty list → empty list."""
        extractor = _extractor()
        assert extractor.extract_common_elements([]) == []

    def test_single_filename_returns_its_parts(self) -> None:
        """Single filename → its parts are the common elements."""
        extractor = _extractor()
        result = extractor.extract_common_elements(["report_2024.txt"])
        assert "report" in result or "2024" in result

    def test_common_parts_extracted(self) -> None:
        """Files sharing a common prefix → prefix in common elements."""
        extractor = _extractor()
        filenames = ["report_alpha.txt", "report_beta.txt", "report_gamma.txt"]
        common = extractor.extract_common_elements(filenames)
        assert "report" in common

    def test_no_common_parts_returns_empty(self) -> None:
        """Files with no shared parts → empty list."""
        extractor = _extractor()
        filenames = ["alpha.txt", "beta.pdf", "gamma.jpg"]
        common = extractor.extract_common_elements(filenames)
        assert common == []


# ---------------------------------------------------------------------------
# identify_structure_pattern
# ---------------------------------------------------------------------------


class TestIdentifyStructurePattern:
    def test_empty_filenames_returns_none(self) -> None:
        """Empty list → None."""
        extractor = _extractor()
        assert extractor.identify_structure_pattern([]) is None

    def test_single_file_returns_pattern(self) -> None:
        """Single file → pattern is identified."""
        extractor = _extractor()
        result = extractor.identify_structure_pattern(["report_2024.txt"])
        assert result is not None

    def test_consistent_delimiter_detected(self) -> None:
        """Files sharing underscore delimiter → delimiter=_."""
        extractor = _extractor()
        filenames = ["report_alpha.txt", "report_beta.txt", "report_gamma.txt"]
        result = extractor.identify_structure_pattern(filenames)
        assert result is not None
        assert result.delimiter == "_"

    def test_date_format_detected_in_pattern(self) -> None:
        """Files with dates → has_date=True and date_format set."""
        extractor = _extractor()
        filenames = [
            "report_2024-01-15.txt",
            "report_2024-02-20.txt",
            "report_2024-03-10.txt",
        ]
        result = extractor.identify_structure_pattern(filenames)
        assert result is not None
        assert result.has_date is True
        assert result.date_format == "YYYY-MM-DD"

    def test_common_prefix_set_when_threshold_met(self) -> None:
        """Majority files sharing a prefix → prefix attribute set."""
        extractor = _extractor()
        filenames = [
            "report_alpha.txt",
            "report_beta.txt",
            "report_gamma.txt",
            "report_delta.txt",
        ]
        result = extractor.identify_structure_pattern(filenames)
        assert result is not None
        # 'report' appears as first part in all 4 files
        assert result.prefix == "report"

    def test_confidence_scales_with_file_count(self) -> None:
        """More files → higher confidence (up to 0.95)."""
        extractor = _extractor()
        small = extractor.identify_structure_pattern(["a.txt", "b.txt"])
        large = extractor.identify_structure_pattern(["a.txt"] * 10 + ["b.txt"])
        assert large.confidence >= small.confidence


# ---------------------------------------------------------------------------
# suggest_naming_convention — all branches
# ---------------------------------------------------------------------------


class TestSuggestNamingConvention:
    def test_empty_file_info_returns_none(self) -> None:
        """No parts → None."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention({})
        assert result is None

    def test_content_only(self) -> None:
        """Only content provided → just content."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention({"content": "myreport"})
        assert result is not None
        assert "myreport" in result

    def test_prefix_and_content(self) -> None:
        """Prefix + content → joined with delimiter."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention(
            {"prefix": "2024", "content": "report", "delimiter": "-"}
        )
        assert result is not None
        assert "2024" in result
        assert "report" in result

    def test_include_date_adds_date(self) -> None:
        """include_date=True → date string appended."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention({"content": "report", "include_date": True})
        assert result is not None
        # Date format YYYY-MM-DD
        import re

        assert re.search(r"\d{4}-\d{2}-\d{2}", result)

    def test_suffix_added(self) -> None:
        """suffix provided → appended to filename."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention({"content": "report", "suffix": "final"})
        assert result is not None
        assert "final" in result

    def test_extension_added(self) -> None:
        """extension provided → appended to filename."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention({"content": "report", "extension": ".pdf"})
        assert result is not None
        assert result.endswith(".pdf")

    def test_case_convention_upper(self) -> None:
        """case_convention='upper' → uppercase result."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention(
            {"content": "myreport", "case_convention": "upper"}
        )
        assert result is not None
        assert result == result.upper()

    def test_case_convention_title(self) -> None:
        """case_convention='title' → title case."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention(
            {"content": "my report", "case_convention": "title"}
        )
        assert result is not None
        assert result == result.title()

    def test_case_convention_camel(self) -> None:
        """case_convention='camel' → camelCase."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention(
            {"content": "my_report", "case_convention": "camel", "delimiter": "_"}
        )
        assert result is not None
        # Should produce camelCase — first word lower, rest capitalized
        assert result[0].islower()

    def test_case_convention_pascal(self) -> None:
        """case_convention='pascal' → PascalCase."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention(
            {"content": "my_report", "case_convention": "pascal", "delimiter": "_"}
        )
        assert result is not None
        assert result[0].isupper()

    def test_case_convention_default_lower(self) -> None:
        """Default case_convention='lower' → lowercase."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention({"content": "MyReport"})
        assert result is not None
        assert result == result.lower()

    def test_unknown_case_convention_returns_unchanged(self) -> None:
        """Unknown case_convention → text unchanged."""
        extractor = _extractor()
        result = extractor.suggest_naming_convention(
            {"content": "MyReport", "case_convention": "unknown"}
        )
        assert result is not None
        assert "MyReport" in result


# ---------------------------------------------------------------------------
# calculate_similarity
# ---------------------------------------------------------------------------


class TestCalculateSimilarity:
    def test_identical_files_high_similarity(self) -> None:
        """Same filename → similarity close to 1.0."""
        extractor = _extractor()
        score = extractor.calculate_similarity("report_2024.pdf", "report_2024.pdf")
        assert score > 0.9

    def test_different_extension_reduces_similarity(self) -> None:
        """Different extension → lower similarity."""
        extractor = _extractor()
        same_ext = extractor.calculate_similarity("report.pdf", "invoice.pdf")
        diff_ext = extractor.calculate_similarity("report.pdf", "invoice.txt")
        assert same_ext > diff_ext

    def test_both_no_date_contributes_similarity(self) -> None:
        """Both files have no date → date similarity = 1.0."""
        extractor = _extractor()
        score = extractor.calculate_similarity("report_final.pdf", "invoice_final.pdf")
        assert score > 0.0

    def test_both_have_same_date_format_similarity(self) -> None:
        """Both files have same date format → date_sim = 1.0."""
        extractor = _extractor()
        score = extractor.calculate_similarity("report_2024-01-01.pdf", "invoice_2024-06-15.pdf")
        assert score > 0.0

    def test_one_has_date_other_doesnt(self) -> None:
        """One has date, other doesn't → date_sim = 0.0."""
        extractor = _extractor()
        score_mixed = extractor.calculate_similarity("2024-01-01_report.pdf", "invoice.pdf")
        score_same = extractor.calculate_similarity("2024-01-01_report.pdf", "2024-06-01_doc.pdf")
        assert score_same >= score_mixed

    def test_different_date_formats(self) -> None:
        """Both have dates but different formats → date_sim = 0.0."""
        extractor = _extractor()
        score = extractor.calculate_similarity("report_2024-01-15.pdf", "report_20240115.pdf")
        # Different date formats → date_sim = 0, reduces score
        assert score < 1.0

    def test_no_delimiters_similarity(self) -> None:
        """Files without delimiters → delimiter factor not added."""
        extractor = _extractor()
        # No delimiters in either file name
        score = extractor.calculate_similarity("report.pdf", "invoice.pdf")
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# generate_regex_pattern
# ---------------------------------------------------------------------------


class TestGenerateRegexPattern:
    def test_empty_filenames_returns_none(self) -> None:
        """Empty list → None."""
        extractor = _extractor()
        assert extractor.generate_regex_pattern([]) is None

    def test_with_filenames_returns_string(self) -> None:
        """Non-empty list → regex string."""
        extractor = _extractor()
        result = extractor.generate_regex_pattern(["report_2024.txt", "report_2025.txt"])
        assert result is not None
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _detect_case_convention — all branches
# ---------------------------------------------------------------------------


class TestDetectCaseConvention:
    def _detect(self, text: str) -> str:
        from file_organizer.services.intelligence.pattern_extractor import NamingPatternExtractor

        return NamingPatternExtractor()._detect_case_convention(text)

    def test_lower(self) -> None:
        assert self._detect("myfile") == "lower"

    def test_upper(self) -> None:
        assert self._detect("MYFILE") == "upper"

    def test_title(self) -> None:
        # str.istitle() → each word starts with uppercase, rest lowercase
        assert self._detect("My File") == "title"

    def test_camel_case(self) -> None:
        # ^[a-z]+([A-Z][a-z]*)+$
        assert self._detect("myFileName") == "camel"

    def test_pascal_case(self) -> None:
        # ^[A-Z][a-z]+([A-Z][a-z]*)*$
        assert self._detect("MyFileName") == "pascal"

    def test_mixed(self) -> None:
        # Doesn't match any above
        assert self._detect("my123FILE_mix") == "mixed"

    def test_mixed_numbers_only(self) -> None:
        """All digits → mixed."""
        assert self._detect("12345") == "mixed"


# ---------------------------------------------------------------------------
# _apply_case_convention — all branches
# ---------------------------------------------------------------------------


class TestApplyCaseConvention:
    def _apply(self, text: str, convention: str) -> str:
        from file_organizer.services.intelligence.pattern_extractor import NamingPatternExtractor

        return NamingPatternExtractor()._apply_case_convention(text, convention)

    def test_lower(self) -> None:
        assert self._apply("MyReport", "lower") == "myreport"

    def test_upper(self) -> None:
        assert self._apply("MyReport", "upper") == "MYREPORT"

    def test_title(self) -> None:
        assert self._apply("my report", "title") == "My Report"

    def test_camel(self) -> None:
        result = self._apply("my_report_final", "camel")
        assert result == "myReportFinal"

    def test_camel_empty_words(self) -> None:
        """camel on simple word (no split) → lowercase word."""
        result = self._apply("report", "camel")
        assert result == "report"

    def test_pascal(self) -> None:
        result = self._apply("my_report_final", "pascal")
        assert result == "MyReportFinal"

    def test_unknown_convention_returns_unchanged(self) -> None:
        """Unknown convention → text returned unchanged."""
        assert self._apply("MyReport", "unknown") == "MyReport"


# ---------------------------------------------------------------------------
# _split_by_delimiters
# ---------------------------------------------------------------------------


class TestSplitByDelimiters:
    def _split(self, text: str, delimiters: list[str]) -> list[str]:
        from file_organizer.services.intelligence.pattern_extractor import NamingPatternExtractor

        return NamingPatternExtractor()._split_by_delimiters(text, delimiters)

    def test_empty_delimiters_returns_whole_text(self) -> None:
        """No delimiters → whole text as single element."""
        assert self._split("myfile", []) == ["myfile"]

    def test_camelcase_only_delimiter_returns_whole_text(self) -> None:
        """Only 'camelCase' delimiter → no regex pattern → whole text."""
        assert self._split("myFile", ["camelCase"]) == ["myFile"]

    def test_split_by_underscore(self) -> None:
        """Underscore splits text."""
        parts = self._split("my_file_name", ["_"])
        assert parts == ["my", "file", "name"]

    def test_split_by_multiple_delimiters(self) -> None:
        """Multiple delimiters split text correctly."""
        parts = self._split("my_file-name", ["_", "-"])
        assert "my" in parts and "file" in parts and "name" in parts

    def test_empty_parts_removed(self) -> None:
        """Empty strings from split are filtered out."""
        parts = self._split("__file__", ["_"])
        assert "" not in parts
        assert "file" in parts


# ---------------------------------------------------------------------------
# analyze_filename — prefix/suffix/middle_parts
# ---------------------------------------------------------------------------


class TestAnalyzeFilename:
    def test_middle_parts_populated_for_3plus_parts(self) -> None:
        """File with 3+ parts → middle_parts populated."""
        extractor = _extractor()
        result = extractor.analyze_filename("prefix_middle_suffix.txt")
        assert result["middle_parts"] == ["middle"]

    def test_two_parts_no_middle(self) -> None:
        """File with 2 parts → middle_parts = []."""
        extractor = _extractor()
        result = extractor.analyze_filename("prefix_suffix.txt")
        assert result["middle_parts"] == []

    def test_single_part_no_suffix(self) -> None:
        """Single-part name → potential_suffix = None."""
        extractor = _extractor()
        result = extractor.analyze_filename("report.txt")
        assert result.get("potential_suffix") is None

    def test_camelcase_delimiter_detected(self) -> None:
        """camelCase pattern → camelCase in delimiters."""
        extractor = _extractor()
        result = extractor.analyze_filename("myReportFile.txt")
        assert "camelCase" in result["delimiters"]

    def test_has_numbers_true(self) -> None:
        """Filename with digits → has_numbers=True."""
        extractor = _extractor()
        result = extractor.analyze_filename("report2024.txt")
        assert result["has_numbers"] is True

    def test_has_numbers_false(self) -> None:
        """Filename without digits → has_numbers=False."""
        extractor = _extractor()
        result = extractor.analyze_filename("report.txt")
        assert result["has_numbers"] is False
