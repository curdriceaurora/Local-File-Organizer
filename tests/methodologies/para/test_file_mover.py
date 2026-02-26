"""Tests for PARA AI File Mover.

Tests cover move suggestion generation, dry-run and actual file moves,
bulk organization, archive suggestions, and collision handling.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.methodologies.para.ai.file_mover import (
    MoveSuggestion,
    OrganizationReport,
    PARAFileMover,
)
from file_organizer.methodologies.para.ai.suggestion_engine import (
    PARASuggestion,
    PARASuggestionEngine,
)
from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig


def _make_para_suggestion(
    category: PARACategory = PARACategory.PROJECT,
    confidence: float = 0.80,
    subfolder: str | None = None,
) -> PARASuggestion:
    """Create a PARASuggestion for mocking."""
    return PARASuggestion(
        category=category,
        confidence=confidence,
        reasoning=["Test reason"],
        suggested_subfolder=subfolder,
    )


@pytest.fixture
def config() -> PARAConfig:
    """Create a default config."""
    return PARAConfig()


@pytest.fixture
def para_root(tmp_path: Path) -> Path:
    """Create a temporary PARA root directory."""
    root = tmp_path / "para_root"
    root.mkdir()
    return root


@pytest.fixture
def mock_suggestion_engine() -> MagicMock:
    """Create a mock suggestion engine."""
    engine = MagicMock(spec=PARASuggestionEngine)
    engine.suggest.return_value = _make_para_suggestion()
    return engine


@pytest.fixture
def mover(
    config: PARAConfig,
    mock_suggestion_engine: MagicMock,
    para_root: Path,
) -> PARAFileMover:
    """Create a PARAFileMover with mocked dependencies."""
    return PARAFileMover(
        config=config,
        suggestion_engine=mock_suggestion_engine,
        root_dir=para_root,
    )


# =========================================================================
# MoveSuggestion tests
# =========================================================================


@pytest.mark.unit
class TestMoveSuggestion:
    """Tests for MoveSuggestion dataclass."""

    def test_valid_creation(self) -> None:
        """Should create a valid suggestion."""
        s = MoveSuggestion(
            file_path=Path("/test/file.txt"),
            target_category=PARACategory.PROJECT,
            target_path=Path("/para/Projects/file.txt"),
            confidence=0.85,
        )
        assert s.confidence == 0.85

    def test_invalid_confidence_raises(self) -> None:
        """Should reject out-of-range confidence."""
        with pytest.raises(ValueError, match="confidence"):
            MoveSuggestion(
                file_path=Path("/test/file.txt"),
                target_category=PARACategory.PROJECT,
                target_path=Path("/para/Projects/file.txt"),
                confidence=1.5,
            )


# =========================================================================
# suggest_move() tests
# =========================================================================


@pytest.mark.unit
class TestSuggestMove:
    """Tests for the suggest_move method."""

    def test_returns_move_suggestion(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Should return a MoveSuggestion."""
        f = tmp_path / "test_file.txt"
        f.write_text("content")
        result = mover.suggest_move(f)
        assert isinstance(result, MoveSuggestion)
        assert result.file_path == f
        assert result.target_category == PARACategory.PROJECT

    def test_target_path_under_root(
        self,
        mover: PARAFileMover,
        para_root: Path,
        tmp_path: Path,
    ) -> None:
        """Target path should be under the PARA root."""
        f = tmp_path / "file.txt"
        f.write_text("content")
        result = mover.suggest_move(f)
        assert str(result.target_path).startswith(str(para_root))

    def test_target_path_includes_category_dir(
        self,
        mover: PARAFileMover,
        para_root: Path,
        tmp_path: Path,
    ) -> None:
        """Target path should include the category directory."""
        f = tmp_path / "file.txt"
        f.write_text("content")
        result = mover.suggest_move(f)
        assert "Projects" in str(result.target_path)

    def test_subfolder_in_target_path(
        self,
        config: PARAConfig,
        para_root: Path,
        tmp_path: Path,
    ) -> None:
        """Subfolder suggestion should appear in the target path."""
        mock_engine = MagicMock(spec=PARASuggestionEngine)
        mock_engine.suggest.return_value = _make_para_suggestion(
            category=PARACategory.RESOURCE,
            subfolder="Guides",
        )
        mover = PARAFileMover(
            config=config,
            suggestion_engine=mock_engine,
            root_dir=para_root,
        )
        f = tmp_path / "tutorial.pdf"
        f.write_bytes(b"pdf content")
        result = mover.suggest_move(f)
        assert "Guides" in str(result.target_path)


# =========================================================================
# move_file() tests
# =========================================================================


@pytest.mark.unit
class TestMoveFile:
    """Tests for the move_file method."""

    def test_dry_run_does_not_move(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Dry run should not actually move the file."""
        f = tmp_path / "original.txt"
        f.write_text("content")
        suggestion = MoveSuggestion(
            file_path=f,
            target_category=PARACategory.PROJECT,
            target_path=mover.root_dir / "Projects" / "original.txt",
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=True)
        assert result.success is True
        assert result.dry_run is True
        assert f.exists()  # File should still be at original location

    def test_actual_move_moves_file(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Actual move should relocate the file."""
        f = tmp_path / "to_move.txt"
        f.write_text("content to move")
        target = mover.root_dir / "Projects" / "to_move.txt"
        suggestion = MoveSuggestion(
            file_path=f,
            target_category=PARACategory.PROJECT,
            target_path=target,
            confidence=0.9,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is True
        assert result.dry_run is False
        assert not f.exists()  # Original should be gone
        assert result.destination.exists()  # Destination should exist

    def test_move_nonexistent_file_fails(
        self,
        mover: PARAFileMover,
    ) -> None:
        """Moving a non-existent file should fail."""
        suggestion = MoveSuggestion(
            file_path=Path("/nonexistent/file.txt"),
            target_category=PARACategory.PROJECT,
            target_path=mover.root_dir / "Projects" / "file.txt",
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is False
        assert result.error is not None

    def test_move_to_same_location_succeeds(
        self,
        mover: PARAFileMover,
        para_root: Path,
    ) -> None:
        """Moving a file to its current location should succeed (no-op)."""
        projects_dir = para_root / "Projects"
        projects_dir.mkdir()
        f = projects_dir / "already_there.txt"
        f.write_text("content")
        suggestion = MoveSuggestion(
            file_path=f,
            target_category=PARACategory.PROJECT,
            target_path=f,
            confidence=0.9,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is True
        assert f.exists()

    def test_collision_resolution(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Should handle filename collisions by appending counter."""
        # Create existing file at target
        target_dir = mover.root_dir / "Projects"
        target_dir.mkdir(parents=True)
        (target_dir / "report.txt").write_text("existing")

        # Create source file
        f = tmp_path / "report.txt"
        f.write_text("new content")

        suggestion = MoveSuggestion(
            file_path=f,
            target_category=PARACategory.PROJECT,
            target_path=target_dir / "report.txt",
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is True
        # Should be renamed to report_1.txt
        assert "report_1.txt" in str(result.destination)

    def test_creates_target_directory(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Should create target directory if it doesn't exist."""
        f = tmp_path / "deep_file.txt"
        f.write_text("content")
        target = mover.root_dir / "Resources" / "Guides" / "deep_file.txt"
        suggestion = MoveSuggestion(
            file_path=f,
            target_category=PARACategory.RESOURCE,
            target_path=target,
            confidence=0.7,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is True


# =========================================================================
# bulk_organize() tests
# =========================================================================


@pytest.mark.unit
class TestBulkOrganize:
    """Tests for the bulk_organize method."""

    def test_empty_directory_returns_empty_report(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Empty directory should produce zero-count report."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        report = mover.bulk_organize(empty_dir)
        assert report.total_files == 0
        assert report.moved == 0

    def test_nonexistent_directory(
        self,
        mover: PARAFileMover,
    ) -> None:
        """Non-existent directory should return empty report."""
        report = mover.bulk_organize(Path("/nonexistent/dir"))
        assert report.total_files == 0

    def test_dry_run_counts_files(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Dry run should count files but not move them."""
        src = tmp_path / "source"
        src.mkdir()
        for i in range(3):
            (src / f"file_{i}.txt").write_text(f"content {i}")

        report = mover.bulk_organize(src, dry_run=True)
        assert report.total_files == 3
        # Files should still exist in original location
        assert len(list(src.iterdir())) == 3

    def test_low_confidence_skipped(
        self,
        config: PARAConfig,
        para_root: Path,
        tmp_path: Path,
    ) -> None:
        """Files with low confidence should be skipped."""
        mock_engine = MagicMock(spec=PARASuggestionEngine)
        mock_engine.suggest.return_value = _make_para_suggestion(confidence=0.3)
        mover = PARAFileMover(
            config=config,
            suggestion_engine=mock_engine,
            root_dir=para_root,
        )
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("content")

        report = mover.bulk_organize(src, dry_run=True, min_confidence=0.6)
        assert report.skipped == 1
        assert report.moved == 0

    def test_report_has_category_distribution(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Report should include category distribution."""
        src = tmp_path / "source"
        src.mkdir()
        for i in range(3):
            (src / f"file_{i}.txt").write_text(f"content {i}")

        report = mover.bulk_organize(src, dry_run=True)
        # All should be PROJECT (from mock)
        if report.moved > 0:
            assert "project" in report.category_distribution

    def test_success_rate_property(self) -> None:
        """success_rate should compute correctly."""
        report = OrganizationReport(total_files=10, moved=7, skipped=2, errors=1)
        assert report.success_rate == pytest.approx(0.7)

    def test_success_rate_zero_files(self) -> None:
        """success_rate should be 0 with no files."""
        report = OrganizationReport(total_files=0)
        assert report.success_rate == 0.0


# =========================================================================
# suggest_archive() tests
# =========================================================================


@pytest.mark.unit
class TestSuggestArchive:
    """Tests for the suggest_archive method."""

    def test_old_files_suggested_for_archive(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Files older than threshold should be suggested for archive."""
        src = tmp_path / "old_files"
        src.mkdir()
        f = src / "ancient.txt"
        f.write_text("old content")

        # Set modification time to 200 days ago
        old_time = time.time() - (200 * 86400)
        import os

        os.utime(f, (old_time, old_time))

        suggestions = mover.suggest_archive(src, inactive_days=180)
        assert len(suggestions) >= 1
        assert suggestions[0].target_category == PARACategory.ARCHIVE

    def test_recent_files_not_suggested(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Recent files should not be suggested for archive."""
        src = tmp_path / "recent"
        src.mkdir()
        f = src / "new_file.txt"
        f.write_text("fresh content")  # Just created = recent

        suggestions = mover.suggest_archive(src, inactive_days=180)
        assert len(suggestions) == 0

    def test_archive_suggestions_sorted_by_confidence(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Archive suggestions should be sorted by confidence (descending)."""
        src = tmp_path / "mixed"
        src.mkdir()

        # Create files with different ages
        for days_old in [200, 300, 190]:
            f = src / f"file_{days_old}d.txt"
            f.write_text(f"content {days_old}")
            old_time = time.time() - (days_old * 86400)
            import os

            os.utime(f, (old_time, old_time))

        suggestions = mover.suggest_archive(src, inactive_days=180)
        if len(suggestions) > 1:
            confidences = [s.confidence for s in suggestions]
            assert confidences == sorted(confidences, reverse=True)

    def test_nonexistent_directory_returns_empty(
        self,
        mover: PARAFileMover,
    ) -> None:
        """Non-existent directory should return empty list."""
        result = mover.suggest_archive(Path("/nonexistent"))
        assert result == []

    def test_archive_reasoning_includes_days(
        self,
        mover: PARAFileMover,
        tmp_path: Path,
    ) -> None:
        """Archive suggestion reasoning should mention inactivity days."""
        src = tmp_path / "old"
        src.mkdir()
        f = src / "stale.txt"
        f.write_text("stale")
        old_time = time.time() - (250 * 86400)
        import os

        os.utime(f, (old_time, old_time))

        suggestions = mover.suggest_archive(src, inactive_days=180)
        assert len(suggestions) >= 1
        assert any("days" in r for r in suggestions[0].reasoning)
