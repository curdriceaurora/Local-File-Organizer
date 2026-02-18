"""Tests for PARA AI Feature Extractor.

Tests cover text feature extraction, metadata feature extraction,
and structural feature extraction without any external dependencies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.methodologies.para.ai.feature_extractor import (
    FeatureExtractor,
)


@pytest.fixture
def extractor() -> FeatureExtractor:
    """Create a default FeatureExtractor."""
    return FeatureExtractor()


@pytest.fixture
def tmp_file(tmp_path: Path) -> Path:
    """Create a temporary file for metadata testing."""
    f = tmp_path / "test_document.txt"
    f.write_text("Sample content for testing.")
    return f


@pytest.fixture
def tmp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with project structure indicators."""
    project = tmp_path / "my-project"
    project.mkdir()
    (project / "README.md").write_text("# My Project")
    (project / "pyproject.toml").write_text("[project]\nname = 'test'")
    (project / "report.pdf").write_bytes(b"fake pdf")
    return project


# =========================================================================
# TextFeatures extraction tests
# =========================================================================


class TestExtractTextFeatures:
    """Tests for extract_text_features method."""

    def test_empty_content_returns_defaults(self, extractor: FeatureExtractor) -> None:
        """Empty content should return a TextFeatures with all defaults."""
        features = extractor.extract_text_features("")
        assert features.word_count == 0
        assert features.keywords == []
        assert features.temporal_indicators == []
        assert features.action_items == []
        assert features.document_type == "unknown"

    def test_whitespace_only_returns_defaults(self, extractor: FeatureExtractor) -> None:
        """Whitespace-only content should be treated as empty."""
        features = extractor.extract_text_features("   \n\t  ")
        assert features.word_count == 0

    def test_word_count_accurate(self, extractor: FeatureExtractor) -> None:
        """Word count should match the number of whitespace-separated tokens."""
        features = extractor.extract_text_features("one two three four five")
        assert features.word_count == 5

    def test_detects_temporal_indicators_dates(self, extractor: FeatureExtractor) -> None:
        """Should detect date patterns like YYYY-MM-DD."""
        text = "The deadline is 2024-03-15 and the launch is on 2024-06-01."
        features = extractor.extract_text_features(text)
        assert len(features.temporal_indicators) >= 2

    def test_detects_temporal_indicators_keywords(self, extractor: FeatureExtractor) -> None:
        """Should detect temporal keywords like deadline, due date."""
        text = "The deadline for this sprint is approaching. Due by Friday."
        features = extractor.extract_text_features(text)
        assert len(features.temporal_indicators) >= 1

    def test_detects_quarter_references(self, extractor: FeatureExtractor) -> None:
        """Should detect quarter references like Q1 2024."""
        text = "Our goals for Q2 2024 include improving performance."
        features = extractor.extract_text_features(text)
        assert len(features.temporal_indicators) >= 1

    def test_detects_action_items_checkboxes(self, extractor: FeatureExtractor) -> None:
        """Should detect markdown checkbox patterns."""
        text = "- [ ] Task one\n- [x] Task two\n- [ ] Task three"
        features = extractor.extract_text_features(text)
        assert len(features.action_items) >= 2

    def test_detects_action_items_todo(self, extractor: FeatureExtractor) -> None:
        """Should detect TODO markers."""
        text = "TODO: Fix the build pipeline. FIXME: Handle edge case."
        features = extractor.extract_text_features(text)
        assert len(features.action_items) >= 1

    def test_counts_project_keywords(self, extractor: FeatureExtractor) -> None:
        """Should count project-related keywords."""
        text = "This project has a deadline and three milestones to deliver."
        features = extractor.extract_text_features(text)
        assert features.category_keyword_counts.get("project", 0) > 0

    def test_counts_area_keywords(self, extractor: FeatureExtractor) -> None:
        """Should count area-related keywords."""
        text = "Ongoing maintenance routine: weekly check of health dashboard."
        features = extractor.extract_text_features(text)
        assert features.category_keyword_counts.get("area", 0) > 0

    def test_counts_resource_keywords(self, extractor: FeatureExtractor) -> None:
        """Should count resource-related keywords."""
        text = "This is a reference guide and tutorial for documentation best practices."
        features = extractor.extract_text_features(text)
        assert features.category_keyword_counts.get("resource", 0) > 0

    def test_counts_archive_keywords(self, extractor: FeatureExtractor) -> None:
        """Should count archive-related keywords."""
        text = "This legacy document is deprecated and obsolete."
        features = extractor.extract_text_features(text)
        assert features.category_keyword_counts.get("archive", 0) > 0

    def test_detects_report_document_type(self, extractor: FeatureExtractor) -> None:
        """Should detect report-type documents."""
        text = "Quarterly report with summary of findings and detailed analysis."
        features = extractor.extract_text_features(text)
        assert features.document_type == "report"

    def test_detects_plan_document_type(self, extractor: FeatureExtractor) -> None:
        """Should detect plan-type documents."""
        text = "Project plan with roadmap, strategy, and timeline for delivery."
        features = extractor.extract_text_features(text)
        assert features.document_type == "plan"

    def test_detects_reference_document_type(self, extractor: FeatureExtractor) -> None:
        """Should detect reference-type documents."""
        text = "API reference guide and manual with documentation for each endpoint."
        features = extractor.extract_text_features(text)
        assert features.document_type == "reference"

    def test_keywords_are_sorted_and_unique(self, extractor: FeatureExtractor) -> None:
        """Keywords list should be sorted and deduplicated."""
        text = "deadline deadline deadline milestone milestone goal goal goal"
        features = extractor.extract_text_features(text)
        assert features.keywords == sorted(set(features.keywords))

    def test_truncation_at_max_length(self) -> None:
        """Content beyond max_content_length should be truncated."""
        short_extractor = FeatureExtractor(max_content_length=100)
        long_text = "deadline " * 200  # Much longer than 100 chars
        features = short_extractor.extract_text_features(long_text)
        # Should still work, just analyzing truncated content
        assert features.word_count < 200


# =========================================================================
# MetadataFeatures extraction tests
# =========================================================================


class TestExtractMetadataFeatures:
    """Tests for extract_metadata_features method."""

    def test_existing_file_returns_metadata(
        self,
        extractor: FeatureExtractor,
        tmp_file: Path,
    ) -> None:
        """Should return populated metadata for an existing file."""
        features = extractor.extract_metadata_features(tmp_file)
        assert features.file_size > 0
        assert features.file_type == ".txt"
        assert features.creation_date is not None
        assert features.modification_date is not None

    def test_nonexistent_file_returns_defaults(self, extractor: FeatureExtractor) -> None:
        """Should return defaults with file_type for non-existent file."""
        features = extractor.extract_metadata_features(Path("/nonexistent/file.pdf"))
        assert features.file_type == ".pdf"
        assert features.file_size == 0
        assert features.creation_date is None

    def test_days_since_modified_is_positive(
        self,
        extractor: FeatureExtractor,
        tmp_file: Path,
    ) -> None:
        """Days since modified should be a non-negative float."""
        features = extractor.extract_metadata_features(tmp_file)
        assert features.days_since_modified >= 0.0

    def test_days_since_created_is_positive(
        self,
        extractor: FeatureExtractor,
        tmp_file: Path,
    ) -> None:
        """Days since created should be a non-negative float."""
        features = extractor.extract_metadata_features(tmp_file)
        assert features.days_since_created >= 0.0

    def test_access_frequency_in_range(
        self,
        extractor: FeatureExtractor,
        tmp_file: Path,
    ) -> None:
        """Access frequency should be between 0.0 and 1.0."""
        features = extractor.extract_metadata_features(tmp_file)
        assert 0.0 <= features.access_frequency <= 1.0

    def test_file_type_extracted_correctly(
        self,
        extractor: FeatureExtractor,
        tmp_path: Path,
    ) -> None:
        """File extension should be correctly extracted."""
        md_file = tmp_path / "notes.md"
        md_file.write_text("# Notes")
        features = extractor.extract_metadata_features(md_file)
        assert features.file_type == ".md"


# =========================================================================
# StructuralFeatures extraction tests
# =========================================================================


class TestExtractStructuralFeatures:
    """Tests for extract_structural_features method."""

    def test_directory_depth(self, extractor: FeatureExtractor, tmp_path: Path) -> None:
        """Should calculate correct directory depth."""
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        f = nested / "deep_file.txt"
        f.write_text("deep")
        features = extractor.extract_structural_features(f)
        assert features.directory_depth >= 3

    def test_sibling_count(
        self,
        extractor: FeatureExtractor,
        tmp_path: Path,
    ) -> None:
        """Should count sibling files correctly."""
        for i in range(5):
            (tmp_path / f"file_{i}.txt").write_text(f"content {i}")
        target = tmp_path / "file_0.txt"
        features = extractor.extract_structural_features(target)
        assert features.sibling_count == 4  # 5 files minus the target

    def test_parent_category_hint_project(
        self,
        extractor: FeatureExtractor,
        tmp_path: Path,
    ) -> None:
        """Should detect 'project' hint from parent directory."""
        proj_dir = tmp_path / "projects"
        proj_dir.mkdir()
        f = proj_dir / "plan.md"
        f.write_text("plan")
        features = extractor.extract_structural_features(f)
        assert features.parent_category_hint == "project"

    def test_parent_category_hint_archive(
        self,
        extractor: FeatureExtractor,
        tmp_path: Path,
    ) -> None:
        """Should detect 'archive' hint from parent directory."""
        arch_dir = tmp_path / "archive"
        arch_dir.mkdir()
        f = arch_dir / "old_doc.txt"
        f.write_text("old content")
        features = extractor.extract_structural_features(f)
        assert features.parent_category_hint == "archive"

    def test_parent_category_hint_none(
        self,
        extractor: FeatureExtractor,
        tmp_path: Path,
    ) -> None:
        """Should return None when parent directory is not a PARA indicator."""
        random_dir = tmp_path / "stuff"
        random_dir.mkdir()
        f = random_dir / "file.txt"
        f.write_text("content")
        features = extractor.extract_structural_features(f)
        assert features.parent_category_hint is None

    def test_has_project_structure(
        self,
        extractor: FeatureExtractor,
        tmp_project_dir: Path,
    ) -> None:
        """Should detect project structure when README/pyproject.toml present."""
        f = tmp_project_dir / "report.pdf"
        features = extractor.extract_structural_features(f)
        assert features.has_project_structure is True

    def test_no_project_structure(
        self,
        extractor: FeatureExtractor,
        tmp_path: Path,
    ) -> None:
        """Should not detect project structure in a plain directory."""
        f = tmp_path / "some_file.txt"
        f.write_text("content")
        features = extractor.extract_structural_features(f)
        assert features.has_project_structure is False

    def test_date_in_path_detected(
        self,
        extractor: FeatureExtractor,
        tmp_path: Path,
    ) -> None:
        """Should detect date patterns in the file path."""
        dated_dir = tmp_path / "2024-01-15"
        dated_dir.mkdir()
        f = dated_dir / "notes.txt"
        f.write_text("notes")
        features = extractor.extract_structural_features(f)
        assert features.has_date_in_path is True

    def test_no_date_in_path(
        self,
        extractor: FeatureExtractor,
        tmp_path: Path,
    ) -> None:
        """Should not detect date when path has no date pattern."""
        f = tmp_path / "regular_file.txt"
        f.write_text("content")
        features = extractor.extract_structural_features(f)
        assert features.has_date_in_path is False

    def test_path_keywords_extracted(
        self,
        extractor: FeatureExtractor,
        tmp_path: Path,
    ) -> None:
        """Should extract keywords found in the file path."""
        ref_dir = tmp_path / "reference"
        ref_dir.mkdir()
        f = ref_dir / "template_guide.txt"
        f.write_text("guide content")
        features = extractor.extract_structural_features(f)
        assert len(features.path_keywords) > 0
        # "reference", "template", "guide" should be found
        assert "reference" in features.path_keywords or "guide" in features.path_keywords
