"""Tests for PARA ai/file_mover uncovered branches.

Targets: MoveSuggestion validation, move_file source not exists,
move_file collision resolution, bulk_organize non-dir, suggest_archive
non-dir, suggest_archive stat error, _resolve_collision overflow.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

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

pytestmark = pytest.mark.unit


class TestPARAFileMoverInit:
    """Cover PARAFileMover.__init__ branches — lines 126-127."""

    def test_init_with_custom_suggestion_engine(self, tmp_path: Path) -> None:
        """Using custom suggestion_engine sets _engine (lines 126-127)."""
        config = PARAConfig()
        custom_engine = PARASuggestionEngine(config=config)
        mover = PARAFileMover(config, suggestion_engine=custom_engine, root_dir=tmp_path)
        assert mover._engine is custom_engine

    def test_root_dir_property(self, tmp_path: Path) -> None:
        """Accessing root_dir property returns _root_dir (line 132)."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        assert mover.root_dir == tmp_path


class TestComputeTargetPath:
    """Cover _compute_target_path with suggested_subfolder — line 381."""

    def test_compute_target_path_with_subfolder(self, tmp_path: Path) -> None:
        """Target path includes suggested_subfolder when provided (line 381)."""
        config = PARAConfig()
        mover = PARAFileMover(config, root_dir=tmp_path)

        file_path = Path("/some/path/document.txt")
        suggestion = PARASuggestion(
            category=PARACategory.PROJECT,
            confidence=0.8,
            reasoning=["test"],
            suggested_subfolder="work/reports",
        )

        target_path = mover._compute_target_path(file_path, suggestion)

        expected = (
            tmp_path
            / config.get_category_directory(PARACategory.PROJECT)
            / "work"
            / "reports"
            / "document.txt"
        )
        assert target_path == expected
        assert target_path.name == "document.txt"


class TestMoveSuggestionValidation:
    """Cover MoveSuggestion.__post_init__ — lines 43-44."""

    def test_confidence_too_high(self) -> None:
        with pytest.raises(ValueError, match=r"between 0.0 and 1.0"):
            MoveSuggestion(
                file_path=Path("/x.txt"),
                target_category=PARACategory.PROJECT,
                target_path=Path("/dst/x.txt"),
                confidence=1.5,
            )

    def test_confidence_too_low(self) -> None:
        with pytest.raises(ValueError, match=r"between 0.0 and 1.0"):
            MoveSuggestion(
                file_path=Path("/x.txt"),
                target_category=PARACategory.PROJECT,
                target_path=Path("/dst/x.txt"),
                confidence=-0.1,
            )


class TestOrganizationReport:
    """Cover OrganizationReport.success_rate — lines 91-93."""

    def test_success_rate_zero_total(self) -> None:
        report = OrganizationReport(total_files=0, moved=0)
        assert report.success_rate == 0.0

    def test_success_rate_with_files(self) -> None:
        report = OrganizationReport(total_files=10, moved=7)
        assert report.success_rate == pytest.approx(0.7)


class TestMoveFile:
    """Cover move_file branches — lines 222-224, 258, 276-277, 289-293."""

    def test_source_not_exists(self, tmp_path: Path) -> None:
        """Source file missing returns error (lines 178-185)."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        suggestion = MoveSuggestion(
            file_path=tmp_path / "missing.txt",
            target_category=PARACategory.PROJECT,
            target_path=tmp_path / "Projects" / "missing.txt",
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is False
        assert "does not exist" in result.error

    def test_source_already_at_destination(self, tmp_path: Path) -> None:
        """Source == destination returns success."""
        f = tmp_path / "file.txt"
        f.write_text("content")
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        suggestion = MoveSuggestion(
            file_path=f,
            target_category=PARACategory.PROJECT,
            target_path=f,
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is True

    def test_move_file_os_error(self, tmp_path: Path) -> None:
        """OSError during move returns error (lines 222-224)."""
        src = tmp_path / "src.txt"
        src.write_text("content")
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        suggestion = MoveSuggestion(
            file_path=src,
            target_category=PARACategory.PROJECT,
            target_path=Path("/proc/impossible/dst.txt"),
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is False
        assert result.error is not None

    def test_move_file_collision_resolution(self, tmp_path: Path) -> None:
        """When target exists, collision resolution appends counter (lines 448-450)."""
        src = tmp_path / "src.txt"
        src.write_text("source")
        dst_dir = tmp_path / "Projects"
        dst_dir.mkdir()
        (dst_dir / "src.txt").write_text("existing")

        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        suggestion = MoveSuggestion(
            file_path=src,
            target_category=PARACategory.PROJECT,
            target_path=dst_dir / "src.txt",
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=False)
        assert result.success is True
        assert result.destination.name == "src_1.txt"

    def test_move_file_dry_run(self, tmp_path: Path) -> None:
        """Dry run logs but doesn't move file (line 198)."""
        src = tmp_path / "src.txt"
        src.write_text("content")
        dst_dir = tmp_path / "Projects"
        dst_dir.mkdir()

        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        suggestion = MoveSuggestion(
            file_path=src,
            target_category=PARACategory.PROJECT,
            target_path=dst_dir / "src.txt",
            confidence=0.8,
        )
        result = mover.move_file(suggestion, dry_run=True)
        assert result.success is True
        assert result.dry_run is True
        # Original file should still exist
        assert src.exists()
        assert not (dst_dir / "src.txt").exists()


class TestBulkOrganize:
    """Cover bulk_organize branches — lines 258, 276-277, 289-293."""

    def test_bulk_organize_nonexistent_dir(self, tmp_path: Path) -> None:
        """Non-existent directory returns empty report (line 253-254)."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        report = mover.bulk_organize(tmp_path / "nonexistent")
        assert report.total_files == 0

    def test_bulk_organize_low_confidence_skipped(self, tmp_path: Path) -> None:
        """Files with low confidence are skipped (line 270-271)."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("hello")

        config = PARAConfig()
        mock_suggestion = MagicMock()
        mock_suggestion.category = PARACategory.PROJECT
        mock_suggestion.confidence = 0.1
        mock_suggestion.reasoning = ["low"]
        mock_suggestion.suggested_subfolder = None

        engine = MagicMock()
        engine.suggest.return_value = mock_suggestion
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        report = mover.bulk_organize(src_dir, min_confidence=0.5)
        assert report.skipped == 1  # exactly 1 file placed in source

    def test_bulk_organize_error_handling(self, tmp_path: Path) -> None:
        """Exception during processing increments errors (lines 291-293)."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("hello")

        config = PARAConfig()
        engine = MagicMock()
        engine.suggest.side_effect = RuntimeError("engine failure")
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        report = mover.bulk_organize(src_dir)
        assert report.errors == 1  # exactly 1 file placed in source

    def test_bulk_organize_recursive(self, tmp_path: Path) -> None:
        """Recursive mode scans subdirectories (lines 257-260)."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        subdir = src_dir / "subdir"
        subdir.mkdir()
        (src_dir / "file1.txt").write_text("top level")
        (subdir / "file2.txt").write_text("nested")

        config = PARAConfig()
        mock_suggestion = MagicMock()
        mock_suggestion.category = PARACategory.PROJECT
        mock_suggestion.confidence = 0.8
        mock_suggestion.reasoning = ["test"]
        mock_suggestion.suggested_subfolder = None

        engine = MagicMock()
        engine.suggest.return_value = mock_suggestion
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)

        # Non-recursive should only find file1.txt
        report_non_recursive = mover.bulk_organize(src_dir, recursive=False, dry_run=True)
        assert report_non_recursive.total_files == 1

        # Recursive should find both files
        report_recursive = mover.bulk_organize(src_dir, recursive=True, dry_run=True)
        assert report_recursive.total_files == 2

    def test_bulk_organize_already_organized(self, tmp_path: Path) -> None:
        """Files already in correct location are skipped (lines 276-277)."""
        projects_dir = tmp_path / "Projects"
        projects_dir.mkdir()
        file_in_projects = projects_dir / "already_here.txt"
        file_in_projects.write_text("content")

        config = PARAConfig()
        mock_suggestion = MagicMock()
        mock_suggestion.category = PARACategory.PROJECT
        mock_suggestion.confidence = 0.8
        mock_suggestion.reasoning = ["test"]
        mock_suggestion.suggested_subfolder = None

        engine = MagicMock()
        engine.suggest.return_value = mock_suggestion
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)

        report = mover.bulk_organize(projects_dir, dry_run=True)
        # File is already in Projects, so it should be skipped
        assert report.skipped == 1  # exactly 1 file placed in source
        assert report.moved == 0

    def test_bulk_organize_move_fails(self, tmp_path: Path) -> None:
        """Failed moves increment error count (line 289)."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("content")

        config = PARAConfig()
        mock_suggestion = MagicMock()
        mock_suggestion.category = PARACategory.PROJECT
        mock_suggestion.confidence = 0.8
        mock_suggestion.reasoning = ["test"]
        mock_suggestion.suggested_subfolder = None

        engine = MagicMock()
        engine.suggest.return_value = mock_suggestion
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)

        # Mock move_file to return failure
        def mock_move_file(suggestion, dry_run=True):
            from file_organizer.methodologies.para.ai.file_mover import MoveResult

            return MoveResult(
                success=False,
                source=suggestion.file_path,
                destination=suggestion.target_path,
                error="Mock move failure",
                dry_run=dry_run,
            )

        with patch.object(mover, "move_file", side_effect=mock_move_file):
            report = mover.bulk_organize(src_dir, dry_run=True)

        assert report.errors == 1  # exactly 1 file placed in source
        assert report.moved == 0


class TestSuggestArchive:
    """Cover suggest_archive branches — lines 324-326, 352-353."""

    def test_suggest_archive_non_dir(self, tmp_path: Path) -> None:
        """Non-directory returns empty list."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        result = mover.suggest_archive(tmp_path / "nonexistent")
        assert result == []

    def test_suggest_archive_old_files(self, tmp_path: Path) -> None:
        """Files older than threshold are suggested for archive."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        old_file = src_dir / "old.txt"
        old_file.write_text("old content")

        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)

        # Patch time.time to make file appear old
        with patch("file_organizer.methodologies.para.ai.file_mover.time") as mock_time:
            mock_time.time.return_value = time.time() + 200 * 86400
            suggestions = mover.suggest_archive(src_dir, inactive_days=180)

        assert len(suggestions) == 1  # exactly 1 file placed in source
        assert suggestions[0].target_category == PARACategory.ARCHIVE

    def test_suggest_archive_os_error_during_scan(self, tmp_path: Path) -> None:
        """OSError during directory scan returns empty list (lines 324-326)."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)

        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Mock rglob to raise OSError
        with patch.object(Path, "rglob", side_effect=OSError("Permission denied")):
            suggestions = mover.suggest_archive(src_dir)

        assert suggestions == []

    def test_suggest_archive_file_stat_error(self, tmp_path: Path) -> None:
        """OSError during file.stat() is caught and file skipped."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        file1 = src_dir / "file1.txt"
        file1.write_text("content1")
        file2 = src_dir / "file2.txt"
        file2.write_text("content2")

        original_stat = Path.stat

        def mock_stat(self: Path, **kwargs: object) -> object:
            if self.name == "file1.txt":
                raise OSError("Cannot stat file")
            return original_stat(self, **kwargs)

        with patch.object(Path, "is_file", return_value=True):
            with patch.object(Path, "stat", mock_stat):
                with patch("file_organizer.methodologies.para.ai.file_mover.time") as mock_time:
                    mock_time.time.return_value = time.time() + (200 * 86400)
                    suggestions = mover.suggest_archive(src_dir, inactive_days=180)

        # Should have suggestion for file2 only, file1 was skipped
        assert len(suggestions) == 1
        assert suggestions[0].file_path.name == "file2.txt"

    def test_suggest_archive_recent_files_not_suggested(self, tmp_path: Path) -> None:
        """Recent files are not suggested for archive (branch 333->328)."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        recent_file = src_dir / "recent.txt"
        recent_file.write_text("fresh content")

        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)

        # Don't patch time, so file appears recent
        suggestions = mover.suggest_archive(src_dir, inactive_days=180)

        # Recent file should NOT be suggested
        assert len(suggestions) == 0


class TestIsAlreadyOrganized:
    """Cover _is_already_organized exception handling — lines 422-426."""

    def test_is_already_organized_with_path_error(self, tmp_path: Path) -> None:
        """OSError/ValueError during path resolution returns False (lines 422-426)."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)

        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        # Mock resolve to raise OSError
        with patch.object(Path, "resolve", side_effect=OSError("Path resolution error")):
            result = mover._is_already_organized(file_path, PARACategory.PROJECT)
            assert result is False

    def test_is_already_organized_with_value_error(self, tmp_path: Path) -> None:
        """ValueError during is_relative_to check returns False (lines 422-426)."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)

        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        # Mock is_relative_to to raise ValueError
        original_resolve = Path.resolve

        def mock_resolve(self):
            result = original_resolve(self)
            if self == file_path:
                # Create a mock that raises ValueError on is_relative_to
                mock_path = MagicMock(spec=Path)
                mock_path.is_relative_to.side_effect = ValueError("Invalid path comparison")
                mock_path.__eq__ = lambda s, o: False
                return mock_path
            return result

        with patch.object(Path, "resolve", mock_resolve):
            result = mover._is_already_organized(file_path, PARACategory.PROJECT)
            assert result is False


class TestResolveCollision:
    """Cover _resolve_collision overflow — lines 449-453."""

    def test_resolve_collision_no_conflict(self, tmp_path: Path) -> None:
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        dest = tmp_path / "new_file.txt"
        result = mover._resolve_collision(dest)
        assert result == dest

    def test_resolve_collision_finds_alternative(self, tmp_path: Path) -> None:
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        dest = tmp_path / "file.txt"
        dest.write_text("existing")
        result = mover._resolve_collision(dest)
        assert result.name == "file_1.txt"

    def test_resolve_collision_overflow(self, tmp_path: Path) -> None:
        """Collision counter overflow raises OSError (lines 451-455)."""
        config = PARAConfig()
        engine = MagicMock()
        mover = PARAFileMover(config, suggestion_engine=engine, root_dir=tmp_path)
        dest = tmp_path / "file.txt"
        dest.write_text("original")

        # Mock exists to always return True, simulating infinite collision
        with patch.object(Path, "exists", return_value=True):
            with pytest.raises(OSError, match="too many existing files"):
                mover._resolve_collision(dest)
