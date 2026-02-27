"""Integration tests for PARA Smart Suggestions.

End-to-end tests that exercise the full suggestion pipeline from
feature extraction through suggestion generation, feedback collection,
and file organization. All tests use real (non-mocked) components but
do not require Ollama or any AI models.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from file_organizer.methodologies.para.ai.feedback import (
    FeedbackCollector,
    PatternLearner,
)
from file_organizer.methodologies.para.ai.file_mover import PARAFileMover
from file_organizer.methodologies.para.ai.suggestion_engine import (
    PARASuggestion,
    PARASuggestionEngine,
)
from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig


@pytest.fixture
def config() -> PARAConfig:
    """Create a PARA config with AI heuristic disabled."""
    return PARAConfig(enable_ai_heuristic=False)


@pytest.fixture
def engine(config: PARAConfig) -> PARASuggestionEngine:
    """Create a real suggestion engine (no mocks)."""
    return PARASuggestionEngine(config=config)


@pytest.fixture
def mover(config: PARAConfig, tmp_path: Path) -> PARAFileMover:
    """Create a real file mover pointing at a temp PARA root."""
    root = tmp_path / "PARA"
    root.mkdir()
    return PARAFileMover(config=config, root_dir=root)


@pytest.fixture
def collector(tmp_path: Path) -> FeedbackCollector:
    """Create a feedback collector with temp storage."""
    return FeedbackCollector(storage_dir=tmp_path / "feedback")


@pytest.mark.unit
class TestFullPipeline:
    """End-to-end integration tests for the suggestion pipeline."""

    def test_suggest_project_file(
        self,
        engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """A file in a projects directory with project content should suggest PROJECT."""
        proj_dir = tmp_path / "projects" / "website-redesign"
        proj_dir.mkdir(parents=True)
        (proj_dir / "README.md").write_text("# Project")
        f = proj_dir / "plan.md"
        f.write_text(
            "Project plan for Q1 2024.\n"
            "Deadline: March 15, 2024.\n"
            "- [ ] Design mockups\n"
            "- [ ] Implement frontend\n"
            "Sprint 1 milestone: Complete wireframes."
        )
        suggestion = engine.suggest(f, content=f.read_text())
        assert isinstance(suggestion, PARASuggestion)
        # Should strongly favor PROJECT
        combined = suggestion.metadata.get("combined_scores", {})
        project_score = combined.get("project", 0)
        # PROJECT should be a strong contender
        assert project_score > 0.1

    def test_suggest_resource_file(
        self,
        engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """A reference document should suggest RESOURCE."""
        ref_dir = tmp_path / "resources" / "guides"
        ref_dir.mkdir(parents=True)
        f = ref_dir / "python-reference-guide.md"
        f.write_text(
            "Python Reference Guide\n"
            "This documentation covers template patterns.\n"
            "A handbook of best practices for learning.\n"
            "Manual for common programming patterns."
        )
        suggestion = engine.suggest(f, content=f.read_text())
        # RESOURCE should be favored due to parent dir + content
        combined = suggestion.metadata.get("combined_scores", {})
        resource_score = combined.get("resource", 0)
        assert resource_score > 0.1

    def test_suggest_archive_file(
        self,
        engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """An old, inactive file should suggest ARCHIVE."""
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        f = archive_dir / "legacy-report-final.txt"
        f.write_text("This legacy report is completed and archived.")
        # Make file old
        old_time = time.time() - (365 * 86400)
        os.utime(f, (old_time, old_time))

        suggestion = engine.suggest(f, content=f.read_text())
        combined = suggestion.metadata.get("combined_scores", {})
        archive_score = combined.get("archive", 0)
        assert archive_score > 0.1

    def test_batch_suggest_multiple_files(
        self,
        engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """Batch suggestion should process multiple files."""
        files: list[Path] = []
        for name in ["plan.txt", "guide.txt", "old.txt"]:
            f = tmp_path / name
            f.write_text(f"content for {name}")
            files.append(f)

        results = engine.suggest_batch(files)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, PARASuggestion)

    def test_explain_produces_readable_output(
        self,
        engine: PARASuggestionEngine,
        tmp_path: Path,
    ) -> None:
        """Explanation should be a non-empty formatted string."""
        f = tmp_path / "test.txt"
        f.write_text("some content")
        suggestion = engine.suggest(f)
        explanation = engine.explain(suggestion)
        assert isinstance(explanation, str)
        assert len(explanation) > 20
        assert "Recommended category" in explanation

    def test_suggest_and_move_dry_run(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Full pipeline: suggest then move in dry-run mode."""
        f = tmp_path / "report.txt"
        f.write_text("Quarterly report with findings.")
        move_suggestion = mover.suggest_move(f)
        result = mover.move_file(move_suggestion, dry_run=True)
        assert result.success is True
        assert result.dry_run is True
        assert f.exists()  # File should not have moved

    def test_suggest_and_move_actual(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Full pipeline: suggest then actually move the file."""
        f = tmp_path / "moveable.txt"
        f.write_text("Content to be organized.")
        move_suggestion = mover.suggest_move(f)
        result = mover.move_file(move_suggestion, dry_run=False)
        assert result.success is True
        assert not f.exists()  # File should be moved
        assert result.destination.exists()

    def test_feedback_loop(
        self,
        engine: PARASuggestionEngine,
        collector: FeedbackCollector,
        tmp_path: Path,
    ) -> None:
        """Feedback should be recorded and produce meaningful stats."""
        f = tmp_path / "doc.txt"
        f.write_text("test document")

        suggestion = engine.suggest(f)

        # Accept the suggestion
        collector.record_acceptance(f, suggestion)

        # Reject a second one
        f2 = tmp_path / "doc2.txt"
        f2.write_text("another test")
        suggestion2 = engine.suggest(f2)
        collector.record_rejection(f2, suggestion2, PARACategory.ARCHIVE)

        stats = collector.get_accuracy_stats()
        assert stats.total_events == 2
        assert stats.accepted_count == 1
        assert stats.rejected_count == 1

    def test_pattern_learning_from_feedback(
        self,
        collector: FeedbackCollector,
        tmp_path: Path,
    ) -> None:
        """PatternLearner should extract rules from accumulated feedback."""
        # Record several PDF -> RESOURCE feedbacks
        from file_organizer.methodologies.para.ai.suggestion_engine import PARASuggestion

        for i in range(5):
            suggestion = PARASuggestion(
                category=PARACategory.RESOURCE,
                confidence=0.8,
                reasoning=["reference document"],
            )
            collector.record_acceptance(Path(f"/docs/ref_{i}.pdf"), suggestion)

        learner = PatternLearner(min_occurrences=3)
        events = collector.get_events()
        rules = learner.learn_from_feedback(events)
        # Should learn that .pdf files tend to be RESOURCE
        ext_rules = [r for r in rules if r.pattern_type == "extension"]
        assert len(ext_rules) >= 1

    def test_bulk_organize_integration(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Bulk organize should produce a comprehensive report."""
        src = tmp_path / "messy_folder"
        src.mkdir()
        for i in range(5):
            (src / f"doc_{i}.txt").write_text(f"content {i}")

        report = mover.bulk_organize(src, dry_run=True)
        assert report.total_files == 5
        # All should be either moved or skipped
        assert report.moved + report.skipped + report.errors == report.total_files
