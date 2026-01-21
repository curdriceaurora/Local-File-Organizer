"""
Unit tests for Pattern Extractor

Tests filename analysis, pattern extraction, delimiter detection,
date format recognition, and pattern generation.
"""

import pytest
from pathlib import Path
from file_organizer.services.intelligence.pattern_extractor import (
    NamingPatternExtractor,
    NamingPattern,
    PatternElement,
)


class TestNamingPatternExtractor:
    """Tests for NamingPatternExtractor class."""

    def test_initialization(self):
        """Test extractor initialization."""
        extractor = NamingPatternExtractor()
        assert extractor._pattern_cache == {}

    def test_analyze_filename_simple(self):
        """Test analyzing a simple filename."""
        extractor = NamingPatternExtractor()
        analysis = extractor.analyze_filename("report_2024.pdf")

        assert analysis['original'] == "report_2024.pdf"
        assert analysis['name'] == "report_2024"
        assert analysis['extension'] == ".pdf"
        assert '_' in analysis['delimiters']
        assert analysis['has_numbers'] is True

    def test_analyze_filename_with_date(self):
        """Test analyzing filename with date."""
        extractor = NamingPatternExtractor()
        analysis = extractor.analyze_filename("report_2024-01-15.pdf")

        assert analysis['date_info'] is not None
        assert analysis['date_info']['format'] == 'YYYY-MM-DD'
        assert analysis['date_info']['value'] == '2024-01-15'

    def test_analyze_filename_camelcase(self):
        """Test analyzing camelCase filename."""
        extractor = NamingPatternExtractor()
        analysis = extractor.analyze_filename("myReportFile.txt")

        assert 'camelCase' in analysis['delimiters']
        assert analysis['case_convention'] == 'camel'

    def test_extract_delimiters_underscore(self):
        """Test extracting underscore delimiters."""
        extractor = NamingPatternExtractor()
        delimiters = extractor.extract_delimiters("file_name_here")

        assert '_' in delimiters

    def test_extract_delimiters_hyphen(self):
        """Test extracting hyphen delimiters."""
        extractor = NamingPatternExtractor()
        delimiters = extractor.extract_delimiters("file-name-here")

        assert '-' in delimiters

    def test_extract_delimiters_mixed(self):
        """Test extracting multiple delimiters."""
        extractor = NamingPatternExtractor()
        delimiters = extractor.extract_delimiters("file_name-here.test")

        assert '_' in delimiters
        assert '-' in delimiters
        assert '.' in delimiters

    def test_extract_delimiters_camelcase(self):
        """Test detecting camelCase as delimiter."""
        extractor = NamingPatternExtractor()
        delimiters = extractor.extract_delimiters("fileName")

        assert 'camelCase' in delimiters

    def test_detect_date_format_yyyy_mm_dd(self):
        """Test detecting YYYY-MM-DD date format."""
        extractor = NamingPatternExtractor()
        date_info = extractor.detect_date_format("report_2024-01-15")

        assert date_info is not None
        assert date_info['format'] == 'YYYY-MM-DD'
        assert date_info['value'] == '2024-01-15'

    def test_detect_date_format_dd_mm_yyyy(self):
        """Test detecting DD-MM-YYYY date format."""
        extractor = NamingPatternExtractor()
        date_info = extractor.detect_date_format("report_15-01-2024")

        assert date_info is not None
        assert date_info['format'] == 'DD-MM-YYYY'
        assert date_info['value'] == '15-01-2024'

    def test_detect_date_format_yyyymmdd(self):
        """Test detecting YYYYMMDD date format."""
        extractor = NamingPatternExtractor()
        date_info = extractor.detect_date_format("report_20240115")

        assert date_info is not None
        assert date_info['format'] == 'YYYYMMDD'
        assert date_info['value'] == '20240115'

    def test_detect_date_format_none(self):
        """Test no date format detected."""
        extractor = NamingPatternExtractor()
        date_info = extractor.detect_date_format("simple_report")

        assert date_info is None

    def test_extract_common_elements(self):
        """Test extracting common elements from multiple files."""
        extractor = NamingPatternExtractor()
        filenames = [
            "report_january_2024.pdf",
            "report_february_2024.pdf",
            "report_march_2024.pdf"
        ]

        common = extractor.extract_common_elements(filenames)

        assert 'report' in common
        assert '2024' in common

    def test_extract_common_elements_empty(self):
        """Test extracting common elements from empty list."""
        extractor = NamingPatternExtractor()
        common = extractor.extract_common_elements([])

        assert common == []

    def test_identify_structure_pattern(self):
        """Test identifying common structure pattern."""
        extractor = NamingPatternExtractor()
        filenames = [
            "report_2024-01-15.pdf",
            "report_2024-02-20.pdf",
            "report_2024-03-10.pdf"
        ]

        pattern = extractor.identify_structure_pattern(filenames)

        assert pattern is not None
        assert pattern.delimiter == '_'
        assert pattern.has_date is True
        assert pattern.date_format == 'YYYY-MM-DD'
        assert pattern.prefix == 'report'

    def test_identify_structure_pattern_no_common(self):
        """Test identifying pattern with no commonality."""
        extractor = NamingPatternExtractor()
        filenames = ["abc.txt"]

        pattern = extractor.identify_structure_pattern(filenames)

        assert pattern is not None
        assert pattern.confidence > 0

    def test_suggest_naming_convention(self):
        """Test suggesting naming convention."""
        extractor = NamingPatternExtractor()
        file_info = {
            'prefix': 'report',
            'content': 'monthly',
            'include_date': True,
            'delimiter': '_',
            'case_convention': 'lower',
            'extension': '.pdf'
        }

        suggestion = extractor.suggest_naming_convention(file_info)

        assert suggestion is not None
        assert 'report' in suggestion
        assert 'monthly' in suggestion
        assert '.pdf' in suggestion
        assert '_' in suggestion

    def test_suggest_naming_convention_minimal(self):
        """Test suggesting naming convention with minimal info."""
        extractor = NamingPatternExtractor()
        file_info = {
            'content': 'document',
            'extension': '.txt'
        }

        suggestion = extractor.suggest_naming_convention(file_info)

        assert suggestion is not None
        assert 'document' in suggestion
        assert '.txt' in suggestion

    def test_calculate_similarity_identical(self):
        """Test similarity calculation for identical files."""
        extractor = NamingPatternExtractor()
        similarity = extractor.calculate_similarity(
            "report_2024.pdf",
            "report_2024.pdf"
        )

        assert similarity == 1.0

    def test_calculate_similarity_similar(self):
        """Test similarity calculation for similar files."""
        extractor = NamingPatternExtractor()
        similarity = extractor.calculate_similarity(
            "report_january.pdf",
            "report_february.pdf"
        )

        # Same delimiter, extension, case - should be high
        assert similarity > 0.5

    def test_calculate_similarity_different(self):
        """Test similarity calculation for different files."""
        extractor = NamingPatternExtractor()
        similarity = extractor.calculate_similarity(
            "Report2024.PDF",
            "document-jan.txt"
        )

        # Different everything - should be low
        assert similarity < 0.5

    def test_generate_regex_pattern(self):
        """Test generating regex pattern from examples."""
        extractor = NamingPatternExtractor()
        filenames = [
            "report_2024-01-15.pdf",
            "report_2024-02-20.pdf"
        ]

        regex = extractor.generate_regex_pattern(filenames)

        assert regex is not None
        assert isinstance(regex, str)

    def test_generate_regex_pattern_empty(self):
        """Test generating regex from empty list."""
        extractor = NamingPatternExtractor()
        regex = extractor.generate_regex_pattern([])

        assert regex is None


class TestNamingPattern:
    """Tests for NamingPattern dataclass."""

    def test_create_naming_pattern(self):
        """Test creating a naming pattern."""
        pattern = NamingPattern(
            pattern_id="test123",
            delimiter="_",
            has_date=True,
            date_format="YYYY-MM-DD",
            confidence=0.8
        )

        assert pattern.pattern_id == "test123"
        assert pattern.delimiter == "_"
        assert pattern.has_date is True
        assert pattern.confidence == 0.8

    def test_naming_pattern_defaults(self):
        """Test naming pattern with defaults."""
        pattern = NamingPattern(pattern_id="test")

        assert pattern.elements == []
        assert pattern.delimiter is None
        assert pattern.has_date is False
        assert pattern.example_files == []
        assert pattern.confidence == 0.5

    def test_to_regex_simple(self):
        """Test converting pattern to regex."""
        pattern = NamingPattern(pattern_id="test")
        pattern.elements = [
            PatternElement(
                element_type='prefix',
                value='report',
                position=0,
                is_variable=False
            ),
            PatternElement(
                element_type='delimiter',
                value='_',
                position=1,
                is_variable=False
            )
        ]

        regex = pattern.to_regex()

        assert 'report' in regex
        assert '_' in regex

    def test_to_regex_with_variable(self):
        """Test regex generation with variable elements."""
        pattern = NamingPattern(pattern_id="test")
        pattern.elements = [
            PatternElement(
                element_type='date',
                value='{date}',
                position=0,
                is_variable=True,
                pattern=r'\d{4}-\d{2}-\d{2}'
            )
        ]

        regex = pattern.to_regex()

        assert r'\d{4}-\d{2}-\d{2}' in regex

    def test_to_template(self):
        """Test converting pattern to template."""
        pattern = NamingPattern(pattern_id="test")
        pattern.elements = [
            PatternElement(
                element_type='prefix',
                value='report',
                position=0,
                is_variable=False
            ),
            PatternElement(
                element_type='delimiter',
                value='_',
                position=1,
                is_variable=False
            ),
            PatternElement(
                element_type='date',
                value='{date}',
                position=2,
                is_variable=True
            )
        ]

        template = pattern.to_template()

        assert template == "report_{date}"


class TestPatternElement:
    """Tests for PatternElement dataclass."""

    def test_create_pattern_element(self):
        """Test creating a pattern element."""
        element = PatternElement(
            element_type='prefix',
            value='test',
            position=0,
            is_variable=False
        )

        assert element.element_type == 'prefix'
        assert element.value == 'test'
        assert element.position == 0
        assert element.is_variable is False
        assert element.pattern is None

    def test_create_variable_element(self):
        """Test creating a variable pattern element."""
        element = PatternElement(
            element_type='date',
            value='{date}',
            position=1,
            is_variable=True,
            pattern=r'\d{4}-\d{2}-\d{2}'
        )

        assert element.is_variable is True
        assert element.pattern == r'\d{4}-\d{2}-\d{2}'


class TestPatternExtractionIntegration:
    """Integration tests for pattern extraction."""

    def test_extract_and_apply_pattern(self):
        """Test extracting and applying a pattern."""
        extractor = NamingPatternExtractor()

        # Extract pattern from examples
        examples = [
            "invoice_2024-01-15.pdf",
            "invoice_2024-02-20.pdf",
            "invoice_2024-03-10.pdf"
        ]

        pattern = extractor.identify_structure_pattern(examples)

        assert pattern is not None
        assert pattern.prefix == 'invoice'
        assert pattern.has_date is True
        assert pattern.delimiter == '_'

        # Generate template
        template = pattern.to_template()
        assert 'invoice' in template

    def test_multiple_pattern_extraction(self):
        """Test extracting patterns from different file groups."""
        extractor = NamingPatternExtractor()

        # Group 1: Reports
        reports = [
            "report_january_2024.pdf",
            "report_february_2024.pdf"
        ]

        # Group 2: Invoices
        invoices = [
            "invoice-2024-01-15.pdf",
            "invoice-2024-02-20.pdf"
        ]

        pattern1 = extractor.identify_structure_pattern(reports)
        pattern2 = extractor.identify_structure_pattern(invoices)

        assert pattern1.delimiter == '_'
        assert pattern2.delimiter == '-'
        assert pattern1.prefix == 'report'
        assert pattern2.prefix == 'invoice'

    def test_pattern_similarity_detection(self):
        """Test detecting similar naming patterns."""
        extractor = NamingPatternExtractor()

        # Similar files
        file1 = "document_2024-01-15.pdf"
        file2 = "document_2024-02-20.pdf"

        similarity = extractor.calculate_similarity(file1, file2)

        assert similarity > 0.8  # Should be very similar

        # Different files
        file3 = "ReportJan.txt"
        similarity2 = extractor.calculate_similarity(file1, file3)

        assert similarity2 < similarity  # Should be less similar


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
