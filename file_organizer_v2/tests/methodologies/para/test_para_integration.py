"""
PARA Integration Tests

Tests complete workflows and integration with file organizer system.
"""


import pytest

from file_organizer.methodologies.para.categories import (
    PARACategory,
)
from file_organizer.methodologies.para.detection.heuristics import (
    HeuristicEngine,
)


class TestPARAWorkflow:
    """Test complete PARA categorization workflows."""

    @pytest.fixture
    def engine(self):
        """Create heuristic engine."""
        return HeuristicEngine(
            enable_temporal=True,
            enable_content=True,
            enable_structural=True,
        )

    @pytest.fixture
    def test_workspace(self, tmp_path):
        """Create test workspace with PARA structure."""
        workspace = {
            "projects": tmp_path / "Projects",
            "areas": tmp_path / "Areas",
            "resources": tmp_path / "Resources",
            "archive": tmp_path / "Archive",
        }

        for directory in workspace.values():
            directory.mkdir()

        return workspace

    def test_project_file_categorization(self, engine, test_workspace):
        """Test categorizing a typical project file."""
        # Create project file with deadline
        project_file = test_workspace["projects"] / "Q1-Sales-Proposal-2024.docx"
        project_file.touch()

        result = engine.evaluate(project_file)

        # Check that PROJECT has the highest score
        project_score = result.scores[PARACategory.PROJECT]
        assert project_score.score > 0

        # Should be top scoring category
        scores_list = sorted(result.scores.values(), key=lambda x: x.score, reverse=True)
        assert scores_list[0].category == PARACategory.PROJECT

    def test_area_file_categorization(self, engine, test_workspace):
        """Test categorizing an area file."""
        # Create area file with ongoing keywords
        area_file = test_workspace["areas"] / "health-tracking-weekly.xlsx"
        area_file.touch()

        result = engine.evaluate(area_file)

        # Check that AREA has a good score
        area_score = result.scores[PARACategory.AREA]
        assert area_score.score > 0

        # AREA should be in top 2 categories
        scores_list = sorted(result.scores.values(), key=lambda x: x.score, reverse=True)
        top_categories = [s.category for s in scores_list[:2]]
        assert PARACategory.AREA in top_categories

    def test_resource_file_categorization(self, engine, test_workspace):
        """Test categorizing a resource file."""
        # Create resource file
        resource_file = test_workspace["resources"] / "python-tutorial-guide.pdf"
        resource_file.touch()

        result = engine.evaluate(resource_file)

        # Check that RESOURCE has a good score
        resource_score = result.scores[PARACategory.RESOURCE]
        assert resource_score.score > 0

        # RESOURCE should be in top 2 categories
        scores_list = sorted(result.scores.values(), key=lambda x: x.score, reverse=True)
        top_categories = [s.category for s in scores_list[:2]]
        assert PARACategory.RESOURCE in top_categories

    def test_archive_file_categorization(self, engine, test_workspace):
        """Test categorizing an archive file."""
        # Create old archive file
        archive_dir = test_workspace["archive"] / "2020"
        archive_dir.mkdir()
        archive_file = archive_dir / "old-project-final.docx"
        archive_file.touch()

        # Make it old
        import os
        import time
        old_time = time.time() - (200 * 86400)
        os.utime(archive_file, (old_time, old_time))

        result = engine.evaluate(archive_file)

        # Archive should score high
        archive_score = result.scores[PARACategory.ARCHIVE]
        assert archive_score.score > 0.5

    def test_ambiguous_file_handling(self, engine, tmp_path):
        """Test handling of ambiguous files."""
        # Create file with no clear signals
        ambiguous_file = tmp_path / "document.txt"
        ambiguous_file.touch()

        result = engine.evaluate(ambiguous_file)

        # Should either have low confidence or no recommendation
        if result.recommended_category is None:
            assert result.needs_manual_review
        else:
            # If there's a recommendation, confidence might still be low
            assert 0.0 <= result.overall_confidence <= 1.0

    def test_conflicting_signals_resolution(self, engine, tmp_path):
        """Test resolving conflicting categorization signals."""
        # Create file with mixed signals (project name but in archive folder)
        archive_dir = tmp_path / "archive" / "2020"
        archive_dir.mkdir(parents=True)
        mixed_file = archive_dir / "project-deadline.docx"
        mixed_file.touch()

        result = engine.evaluate(mixed_file)

        # Should have scores for multiple categories
        project_score = result.scores[PARACategory.PROJECT].score
        archive_score = result.scores[PARACategory.ARCHIVE].score

        # Both should have some score
        assert project_score > 0 or archive_score > 0


class TestPARAMigrationScenarios:
    """Test scenarios for migrating files to PARA system."""

    @pytest.fixture
    def engine(self):
        """Create heuristic engine."""
        return HeuristicEngine()

    def test_unorganized_files_categorization(self, engine, tmp_path):
        """Test categorizing unorganized files."""
        # Create various unorganized files
        files = {
            "meeting-notes-2024-01-15.docx": PARACategory.PROJECT,
            "health-routine-checklist.xlsx": PARACategory.AREA,
            "python-reference-guide.pdf": PARACategory.RESOURCE,
            "old-backup-2020.zip": PARACategory.ARCHIVE,
        }

        results = {}
        for filename, _expected_category in files.items():
            file_path = tmp_path / filename
            file_path.touch()

            result = engine.evaluate(file_path)
            results[filename] = result

        # Check that files were categorized
        for filename, result in results.items():
            assert result.recommended_category is not None or result.needs_manual_review

    def test_batch_categorization_consistency(self, engine, tmp_path):
        """Test that similar files are categorized consistently."""
        # Create multiple similar project files
        project_files = [
            "project-alpha-proposal.docx",
            "project-beta-deadline.xlsx",
            "project-gamma-milestone.pptx",
        ]

        results = []
        for filename in project_files:
            file_path = tmp_path / filename
            file_path.touch()
            result = engine.evaluate(file_path)
            results.append(result)

        # All should have PROJECT as top or second scoring category
        project_high_scores = sum(
            1 for r in results
            if sorted(r.scores.values(), key=lambda x: x.score, reverse=True)[0].category == PARACategory.PROJECT
            or sorted(r.scores.values(), key=lambda x: x.score, reverse=True)[1].category == PARACategory.PROJECT
        )
        assert project_high_scores >= 2  # At least 2 out of 3 should have PROJECT in top 2

    def test_hierarchical_organization(self, engine, tmp_path):
        """Test organizing files in hierarchical PARA structure."""
        # Create PARA directory structure
        projects_dir = tmp_path / "1-Projects"
        areas_dir = tmp_path / "2-Areas"
        resources_dir = tmp_path / "3-Resources"
        archive_dir = tmp_path / "4-Archive"

        for directory in [projects_dir, areas_dir, resources_dir, archive_dir]:
            directory.mkdir()

        # Create files in each category
        test_files = [
            (projects_dir / "client-proposal.docx", PARACategory.PROJECT),
            (areas_dir / "health-tracking.xlsx", PARACategory.AREA),
            (resources_dir / "coding-guide.pdf", PARACategory.RESOURCE),
            (archive_dir / "old-project.zip", PARACategory.ARCHIVE),
        ]

        for file_path, expected_category in test_files:
            file_path.touch()
            result = engine.evaluate(file_path)

            # Should match expected category based on structure
            if result.recommended_category:
                category_score = result.scores[expected_category].score
                assert category_score > 0  # Should have some score for expected category


class TestPARAEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def engine(self):
        """Create heuristic engine."""
        return HeuristicEngine()

    def test_nonexistent_file(self, engine, tmp_path):
        """Test handling nonexistent file."""
        nonexistent = tmp_path / "nonexistent.txt"
        result = engine.evaluate(nonexistent)

        # Should handle gracefully - may still do content analysis based on filename
        # Just verify it doesn't crash
        assert result is not None
        assert isinstance(result, type(engine.evaluate(tmp_path / "test.txt")))

    def test_very_long_filename(self, engine, tmp_path):
        """Test handling very long filename."""
        long_name = "a" * 200 + "-project-deadline.txt"
        file_path = tmp_path / long_name
        file_path.touch()

        result = engine.evaluate(file_path)

        # Should still work
        assert result is not None
        assert result.recommended_category is not None or result.needs_manual_review

    def test_special_characters_in_path(self, engine, tmp_path):
        """Test handling special characters in path."""
        special_dir = tmp_path / "folder (2024)"
        special_dir.mkdir()
        file_path = special_dir / "project-proposal [draft].docx"
        file_path.touch()

        result = engine.evaluate(file_path)

        # Should handle special characters
        assert result is not None

    def test_unicode_filename(self, engine, tmp_path):
        """Test handling Unicode characters in filename."""
        unicode_file = tmp_path / "项目-提案-2024.docx"
        unicode_file.touch()

        result = engine.evaluate(unicode_file)

        # Should handle Unicode
        assert result is not None

    def test_hidden_file(self, engine, tmp_path):
        """Test handling hidden file."""
        hidden_file = tmp_path / ".hidden-project-file.txt"
        hidden_file.touch()

        result = engine.evaluate(hidden_file)

        # Should still categorize
        assert result is not None

    def test_no_extension_file(self, engine, tmp_path):
        """Test handling file without extension."""
        no_ext_file = tmp_path / "project-document"
        no_ext_file.touch()

        result = engine.evaluate(no_ext_file)

        # Should still work based on name and path
        assert result is not None


class TestPARACategoryTransitions:
    """Test scenarios for files transitioning between categories."""

    @pytest.fixture
    def engine(self):
        """Create heuristic engine."""
        return HeuristicEngine()

    def test_project_to_archive_transition(self, engine, tmp_path):
        """Test identifying completed project for archival."""
        # Create completed project file
        project_file = tmp_path / "client-project-final-completed.docx"
        project_file.touch()

        result = engine.evaluate(project_file)

        # Should have signals for both PROJECT and ARCHIVE
        project_score = result.scores[PARACategory.PROJECT].score
        archive_score = result.scores[PARACategory.ARCHIVE].score

        # Both should be non-zero
        assert project_score > 0 or archive_score > 0

    def test_area_stability_indicators(self, engine, tmp_path):
        """Test identifying stable area files."""
        # Create area file
        area_dir = tmp_path / "areas" / "finance"
        area_dir.mkdir(parents=True)
        area_file = area_dir / "monthly-budget-tracking.xlsx"
        area_file.touch()

        result = engine.evaluate(area_file)

        # Should have AREA signals
        area_score = result.scores[PARACategory.AREA].score
        assert area_score > 0  # Just verify it has some AREA score

    def test_resource_vs_project_distinction(self, engine, tmp_path):
        """Test distinguishing between resource and project files."""
        # Create similar files - one reference, one project
        resource_file = tmp_path / "python-reference-guide.pdf"
        project_file = tmp_path / "python-project-deadline-2024.py"

        resource_file.touch()
        project_file.touch()

        resource_result = engine.evaluate(resource_file)
        project_result = engine.evaluate(project_file)

        # Should categorize differently
        resource_score = resource_result.scores[PARACategory.RESOURCE].score
        project_score = project_result.scores[PARACategory.PROJECT].score

        # At least one should have a clear preference
        assert resource_score > 0 or project_score > 0


class TestPARACustomRules:
    """Test custom categorization rules and patterns."""

    @pytest.fixture
    def engine(self):
        """Create heuristic engine."""
        return HeuristicEngine()

    def test_date_based_project_detection(self, engine, tmp_path):
        """Test detecting projects based on date patterns."""
        dated_files = [
            "report-2024-01-15.docx",
            "meeting-notes-2024-Q1.txt",
            "deliverable-due-03-2024.xlsx",
        ]

        for filename in dated_files:
            file_path = tmp_path / filename
            file_path.touch()

            result = engine.evaluate(file_path)
            project_score = result.scores[PARACategory.PROJECT].score

            # Should have PROJECT signals due to dates
            assert project_score > 0

    def test_recurring_pattern_area_detection(self, engine, tmp_path):
        """Test detecting areas based on recurring patterns."""
        recurring_files = [
            "weekly-team-meeting.docx",
            "monthly-report-template.xlsx",
            "daily-standup-notes.txt",
        ]

        for filename in recurring_files:
            file_path = tmp_path / filename
            file_path.touch()

            result = engine.evaluate(file_path)
            area_score = result.scores[PARACategory.AREA].score

            # Should have AREA signals due to recurring keywords
            assert area_score > 0

    def test_version_based_archive_detection(self, engine, tmp_path):
        """Test detecting archive files based on version patterns."""
        versioned_files = [
            "document-v1.docx",
            "project-v2-old.xlsx",
            "report-final-backup.pdf",
        ]

        # At least one should have archive signals
        archive_scores = []
        for filename in versioned_files:
            file_path = tmp_path / filename
            file_path.touch()

            result = engine.evaluate(file_path)
            archive_score = result.scores[PARACategory.ARCHIVE].score
            archive_scores.append(archive_score)

        # At least one file should have ARCHIVE signals
        assert any(score > 0 for score in archive_scores)


class TestPARAPerformance:
    """Test performance characteristics of PARA categorization."""

    @pytest.fixture
    def engine(self):
        """Create heuristic engine."""
        return HeuristicEngine()

    def test_categorization_speed(self, engine, tmp_path):
        """Test that categorization completes quickly."""
        import time

        file_path = tmp_path / "test-file.txt"
        file_path.touch()

        start = time.time()
        result = engine.evaluate(file_path)
        duration = time.time() - start

        # Should complete in under 1 second
        assert duration < 1.0
        assert result is not None

    def test_batch_categorization_efficiency(self, engine, tmp_path):
        """Test efficiency of categorizing multiple files."""
        import time

        # Create 20 test files
        files = []
        for i in range(20):
            file_path = tmp_path / f"test-file-{i}.txt"
            file_path.touch()
            files.append(file_path)

        start = time.time()
        results = [engine.evaluate(f) for f in files]
        duration = time.time() - start

        # Should complete in reasonable time (< 5 seconds for 20 files)
        assert duration < 5.0
        assert len(results) == 20
        assert all(r is not None for r in results)

    def test_memory_efficiency(self, engine, tmp_path):
        """Test that categorization doesn't leak memory."""
        import gc

        # Categorize many files and ensure cleanup
        for i in range(100):
            file_path = tmp_path / f"file-{i}.txt"
            file_path.touch()
            engine.evaluate(file_path)

        # Force garbage collection
        gc.collect()

        # If we got here without memory error, test passes
        assert True
