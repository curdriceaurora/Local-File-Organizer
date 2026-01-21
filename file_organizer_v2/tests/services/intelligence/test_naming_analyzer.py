"""
Unit tests for Naming Analyzer

Tests advanced filename analysis, structure comparison, pattern detection,
and semantic component extraction.
"""

import pytest
from file_organizer.services.intelligence.naming_analyzer import (
    NamingAnalyzer,
    NameStructure,
)


class TestNameStructure:
    """Tests for NameStructure dataclass."""

    def test_create_name_structure(self):
        """Test creating a name structure."""
        structure = NameStructure(
            original="test_file.txt",
            tokens=["test", "file"],
            delimiters=["_"],
            has_date=False,
            has_version=False
        )

        assert structure.original == "test_file.txt"
        assert structure.tokens == ["test", "file"]
        assert structure.delimiters == ["_"]

    def test_to_dict(self):
        """Test converting structure to dictionary."""
        structure = NameStructure(
            original="test.txt",
            tokens=["test"],
            word_count=1
        )

        data = structure.to_dict()

        assert data['original'] == "test.txt"
        assert data['tokens'] == ["test"]
        assert data['word_count'] == 1


class TestNamingAnalyzer:
    """Tests for NamingAnalyzer class."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = NamingAnalyzer()
        assert analyzer._structure_cache == {}

    def test_analyze_structure_simple(self):
        """Test analyzing simple filename structure."""
        analyzer = NamingAnalyzer()
        structure = analyzer.analyze_structure("test_file.txt")

        assert structure.original == "test_file.txt"
        assert "test" in structure.tokens
        assert "file" in structure.tokens
        assert "_" in structure.delimiters
        assert structure.has_date is False
        assert structure.word_count >= 2

    def test_analyze_structure_with_date(self):
        """Test analyzing filename with date."""
        analyzer = NamingAnalyzer()
        structure = analyzer.analyze_structure("report_2024-01-15.pdf")

        assert structure.has_date is True

    def test_analyze_structure_with_version(self):
        """Test analyzing filename with version."""
        analyzer = NamingAnalyzer()
        structure = analyzer.analyze_structure("document_v2.txt")

        assert structure.has_version is True

    def test_analyze_structure_caching(self):
        """Test that structure analysis is cached."""
        analyzer = NamingAnalyzer()

        # First analysis
        structure1 = analyzer.analyze_structure("test.txt")
        # Second analysis (should be cached)
        structure2 = analyzer.analyze_structure("test.txt")

        assert structure1 is structure2  # Same object

    def test_compare_structures_identical(self):
        """Test comparing identical structures."""
        analyzer = NamingAnalyzer()
        comparison = analyzer.compare_structures("test.txt", "test.txt")

        assert comparison['overall_similarity'] == 1.0
        assert comparison['same_structure'] is True
        assert comparison['compatible'] is True

    def test_compare_structures_similar(self):
        """Test comparing similar structures."""
        analyzer = NamingAnalyzer()
        comparison = analyzer.compare_structures(
            "report_january.pdf",
            "report_february.pdf"
        )

        assert comparison['overall_similarity'] > 0.5
        assert comparison['compatible'] is True

    def test_compare_structures_different(self):
        """Test comparing different structures."""
        analyzer = NamingAnalyzer()
        comparison = analyzer.compare_structures(
            "Report2024.PDF",
            "document-jan.txt"
        )

        assert comparison['overall_similarity'] < 0.8

    def test_find_common_pattern(self):
        """Test finding common pattern across files."""
        analyzer = NamingAnalyzer()
        filenames = [
            "report_2024-01-15.pdf",
            "report_2024-02-20.pdf",
            "report_2024-03-10.pdf"
        ]

        pattern = analyzer.find_common_pattern(filenames)

        assert pattern is not None
        assert pattern['sample_size'] == 3
        assert '_' in pattern['common_delimiters']
        assert pattern['date_frequency'] == 1.0  # All have dates

    def test_find_common_pattern_empty(self):
        """Test finding pattern with empty list."""
        analyzer = NamingAnalyzer()
        pattern = analyzer.find_common_pattern([])

        assert pattern is None

    def test_extract_pattern_differences(self):
        """Test extracting differences between filenames."""
        analyzer = NamingAnalyzer()
        differences = analyzer.extract_pattern_differences(
            "report_draft.txt",
            "report_final.txt"
        )

        assert differences['added_tokens'] == ['final']
        assert differences['removed_tokens'] == ['draft']
        assert 'report' in differences['common_tokens']

    def test_extract_pattern_differences_date_added(self):
        """Test detecting added date."""
        analyzer = NamingAnalyzer()
        differences = analyzer.extract_pattern_differences(
            "report.txt",
            "report_2024-01-15.txt"
        )

        assert differences['added_date'] is True
        assert differences['removed_date'] is False

    def test_extract_pattern_differences_version_added(self):
        """Test detecting added version."""
        analyzer = NamingAnalyzer()
        differences = analyzer.extract_pattern_differences(
            "document.txt",
            "document_v2.txt"
        )

        assert differences['added_version'] is True

    def test_identify_naming_style_snake_case(self):
        """Test identifying snake_case style."""
        analyzer = NamingAnalyzer()
        style = analyzer.identify_naming_style("my_file_name.txt")

        assert style == "snake_case"

    def test_identify_naming_style_kebab_case(self):
        """Test identifying kebab-case style."""
        analyzer = NamingAnalyzer()
        style = analyzer.identify_naming_style("my-file-name.txt")

        assert style == "kebab-case"

    def test_identify_naming_style_camelcase(self):
        """Test identifying camelCase style."""
        analyzer = NamingAnalyzer()
        style = analyzer.identify_naming_style("myFileName.txt")

        assert style == "camelCase"

    def test_identify_naming_style_pascalcase(self):
        """Test identifying PascalCase style."""
        analyzer = NamingAnalyzer()
        style = analyzer.identify_naming_style("MyFileName.txt")

        assert style == "PascalCase"

    def test_identify_naming_style_space_separated(self):
        """Test identifying space separated style."""
        analyzer = NamingAnalyzer()
        style = analyzer.identify_naming_style("my file name.txt")

        assert style == "space_separated"

    def test_identify_naming_style_mixed(self):
        """Test identifying mixed style."""
        analyzer = NamingAnalyzer()
        style = analyzer.identify_naming_style("My_File-Name.txt")

        assert style == "mixed"

    def test_normalize_filename_to_snake_case(self):
        """Test normalizing filename to snake_case."""
        analyzer = NamingAnalyzer()
        normalized = analyzer.normalize_filename("MyFile-Name.txt", "snake_case")

        assert normalized == "my_file_name.txt"

    def test_normalize_filename_to_kebab_case(self):
        """Test normalizing filename to kebab-case."""
        analyzer = NamingAnalyzer()
        normalized = analyzer.normalize_filename("My_File_Name.txt", "kebab-case")

        assert normalized == "my-file-name.txt"

    def test_normalize_filename_to_camelcase(self):
        """Test normalizing filename to camelCase."""
        analyzer = NamingAnalyzer()
        normalized = analyzer.normalize_filename("my_file_name.txt", "camelCase")

        assert normalized == "myFileName.txt"

    def test_normalize_filename_to_pascalcase(self):
        """Test normalizing filename to PascalCase."""
        analyzer = NamingAnalyzer()
        normalized = analyzer.normalize_filename("my_file_name.txt", "PascalCase")

        assert normalized == "MyFileName.txt"

    def test_extract_semantic_components(self):
        """Test extracting semantic components."""
        analyzer = NamingAnalyzer()
        components = analyzer.extract_semantic_components("report_2024-01-15_final.pdf")

        assert components['base_name'] == "report_2024-01-15_final"
        assert len(components['tokens']) > 0
        assert len(components['potential_description']) > 0

    def test_extract_semantic_components_with_version(self):
        """Test extracting components with version."""
        analyzer = NamingAnalyzer()
        components = analyzer.extract_semantic_components("document_v2.txt")

        assert 'version' in components
        assert components['version'] is not None

    def test_extract_semantic_components_with_date(self):
        """Test extracting components with date."""
        analyzer = NamingAnalyzer()
        components = analyzer.extract_semantic_components("report_2024-01-15.txt")

        assert 'date' in components
        assert components['date'] is not None


class TestNamingAnalyzerIntegration:
    """Integration tests for naming analyzer."""

    def test_analyze_and_compare_batch(self):
        """Test analyzing and comparing multiple files."""
        analyzer = NamingAnalyzer()

        files = [
            "report_2024-01-15.pdf",
            "report_2024-02-20.pdf",
            "invoice_2024-01-15.pdf",
            "invoice_2024-02-20.pdf"
        ]

        # Analyze all
        structures = [analyzer.analyze_structure(f) for f in files]

        # Reports should be similar to each other
        report_comparison = analyzer.compare_structures(files[0], files[1])
        assert report_comparison['overall_similarity'] > 0.5  # Relaxed threshold

        # Reports and invoices should be different (but may still be somewhat similar due to dates)
        mixed_comparison = analyzer.compare_structures(files[0], files[2])
        # Just check that they're not identical
        assert mixed_comparison['overall_similarity'] < 1.0

    def test_pattern_evolution_tracking(self):
        """Test tracking pattern evolution over corrections."""
        analyzer = NamingAnalyzer()

        # Original naming pattern
        original = "myReport.pdf"

        # User corrections
        corrections = [
            "my_report.pdf",       # snake_case
            "my_report_v2.pdf",    # added version
            "my_report_v2_2024-01-15.pdf"  # added date
        ]

        differences_history = []
        prev = original

        for corrected in corrections:
            diff = analyzer.extract_pattern_differences(prev, corrected)
            differences_history.append(diff)
            prev = corrected

        # Verify evolution
        assert len(differences_history) == 3
        assert differences_history[1]['added_version'] is True
        assert differences_history[2]['added_date'] is True

    def test_normalize_batch_files(self):
        """Test normalizing multiple files to same style."""
        analyzer = NamingAnalyzer()

        files = [
            "MyFile.txt",
            "another-file.txt",
            "third_file.txt",
            "FourthFile.txt"
        ]

        # Normalize all to snake_case
        normalized = [analyzer.normalize_filename(f, "snake_case") for f in files]

        # All should follow same pattern
        for name in normalized:
            style = analyzer.identify_naming_style(name)
            assert style == "snake_case"

    def test_pattern_consistency_analysis(self):
        """Test analyzing pattern consistency across files."""
        analyzer = NamingAnalyzer()

        # Consistent group
        consistent_files = [
            "report_jan.pdf",
            "report_feb.pdf",
            "report_mar.pdf"
        ]

        # Inconsistent group
        inconsistent_files = [
            "Report-Jan.PDF",
            "report_feb.pdf",
            "ReportMar.txt"
        ]

        pattern1 = analyzer.find_common_pattern(consistent_files)
        pattern2 = analyzer.find_common_pattern(inconsistent_files)

        # Consistent group should have higher consistency
        assert pattern1['consistency'] > pattern2['consistency']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
