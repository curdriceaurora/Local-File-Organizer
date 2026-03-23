"""Integration tests for the PARA methodology package.

Covers PARACategory, CategoryDefinition, PARAConfig, PARAFolderGenerator,
migration manager data classes, and PARA category detection utilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from file_organizer.methodologies.para.categories import CategoryDefinition

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# PARACategory
# ---------------------------------------------------------------------------


class TestPARACategory:
    """Tests for PARACategory enum."""

    def test_all_categories_exist(self) -> None:
        """Verify all four PARA category values are present in the enum."""
        from file_organizer.methodologies.para.categories import PARACategory

        assert PARACategory.PROJECT.value == "project"
        assert PARACategory.AREA.value == "area"
        assert PARACategory.RESOURCE.value == "resource"
        assert PARACategory.ARCHIVE.value == "archive"

    def test_str_returns_title_case(self) -> None:
        """Verify str() returns the title-cased category name."""
        from file_organizer.methodologies.para.categories import PARACategory

        assert str(PARACategory.PROJECT) == "Project"
        assert str(PARACategory.ARCHIVE) == "Archive"

    def test_description_property(self) -> None:
        """Verify PARACategory descriptions contain the canonical key phrases."""
        from file_organizer.methodologies.para.categories import PARACategory

        desc = PARACategory.PROJECT.description
        assert "Time-bound" in desc and "specific completion" in desc

        desc_area = PARACategory.AREA.description
        assert "Ongoing" in desc_area and "responsibility" in desc_area

    def test_four_categories_total(self) -> None:
        """Verify exactly four PARA categories are defined."""
        from file_organizer.methodologies.para.categories import PARACategory

        assert len(PARACategory) == 4


# ---------------------------------------------------------------------------
# CategoryDefinition
# ---------------------------------------------------------------------------


class TestCategoryDefinition:
    """Tests for CategoryDefinition matching logic."""

    def _make_definition(self, keywords: list[str], patterns: list[str]) -> CategoryDefinition:
        from file_organizer.methodologies.para.categories import (
            CategoryDefinition,
            PARACategory,
        )

        return CategoryDefinition(
            name=PARACategory.PROJECT,
            description="Test category",
            criteria=["has deadline"],
            examples=["sprint", "proposal"],
            keywords=keywords,
            patterns=patterns,
            confidence_threshold=0.75,
        )

    def test_keyword_match_case_insensitive(self) -> None:
        """Verify keyword matching is case-insensitive."""
        defn = self._make_definition(keywords=["deadline", "sprint"], patterns=[])
        assert defn.matches_keyword("Sprint planning document") is True
        assert defn.matches_keyword("DEADLINE approaching") is True
        assert defn.matches_keyword("random file") is False

    def test_keyword_no_match(self) -> None:
        """Verify matches_keyword returns False when no keyword is found."""
        defn = self._make_definition(keywords=["deadline"], patterns=[])
        assert defn.matches_keyword("vacation photos") is False

    def test_pattern_match_glob(self) -> None:
        """Verify glob patterns correctly match and reject filenames."""
        defn = self._make_definition(keywords=[], patterns=["*_project*", "*.plan"])
        assert defn.matches_pattern("website_project_v2.md") is True
        assert defn.matches_pattern("architecture.plan") is True
        assert defn.matches_pattern("random.txt") is False

    def test_pattern_match_case_insensitive(self) -> None:
        """Verify glob pattern matching is case-insensitive."""
        defn = self._make_definition(keywords=[], patterns=["*.PROJECT"])
        assert defn.matches_pattern("my.project") is True

    def test_invalid_threshold_raises(self) -> None:
        """Verify a confidence_threshold > 1.0 raises ValueError."""
        from file_organizer.methodologies.para.categories import (
            CategoryDefinition,
            PARACategory,
        )

        with pytest.raises(ValueError, match="confidence_threshold"):
            CategoryDefinition(
                name=PARACategory.PROJECT,
                description="d",
                criteria=["c"],
                examples=[],
                keywords=[],
                patterns=[],
                confidence_threshold=1.5,
            )

    def test_empty_criteria_raises(self) -> None:
        """Verify an empty criteria list raises ValueError."""
        from file_organizer.methodologies.para.categories import (
            CategoryDefinition,
            PARACategory,
        )

        with pytest.raises(ValueError, match="criteria"):
            CategoryDefinition(
                name=PARACategory.PROJECT,
                description="d",
                criteria=[],
                examples=[],
                keywords=[],
                patterns=[],
            )


# ---------------------------------------------------------------------------
# PARAConfig
# ---------------------------------------------------------------------------


class TestPARAConfig:
    """Tests for PARAConfig defaults and methods."""

    def test_default_folder_names(self) -> None:
        """Verify PARAConfig defaults to the canonical PARA folder names."""
        from file_organizer.methodologies.para.config import PARAConfig

        cfg = PARAConfig()
        assert cfg.project_dir == "Projects"
        assert cfg.area_dir == "Areas"
        assert cfg.resource_dir == "Resources"
        assert cfg.archive_dir == "Archive"

    def test_get_category_directory(self) -> None:
        """Verify get_category_directory returns the correct dir name per category."""
        from file_organizer.methodologies.para.categories import PARACategory
        from file_organizer.methodologies.para.config import PARAConfig

        cfg = PARAConfig()
        assert cfg.get_category_directory(PARACategory.PROJECT) == "Projects"
        assert cfg.get_category_directory(PARACategory.AREA) == "Areas"
        assert cfg.get_category_directory(PARACategory.RESOURCE) == "Resources"
        assert cfg.get_category_directory(PARACategory.ARCHIVE) == "Archive"

    def test_get_threshold_for_category(self) -> None:
        """Verify get_category_threshold returns a float in the valid [0, 1] range."""
        from file_organizer.methodologies.para.categories import PARACategory
        from file_organizer.methodologies.para.config import PARAConfig

        cfg = PARAConfig()
        threshold = cfg.get_category_threshold(PARACategory.PROJECT)
        assert 0.0 <= threshold <= 1.0

    def test_get_category_keywords(self) -> None:
        """Verify get_category_keywords returns a non-empty list."""
        from file_organizer.methodologies.para.categories import PARACategory
        from file_organizer.methodologies.para.config import PARAConfig

        cfg = PARAConfig()
        keywords = cfg.get_category_keywords(PARACategory.PROJECT)
        assert isinstance(keywords, list)
        assert len(keywords) >= 1

    def test_load_config_returns_para_config(self) -> None:
        """Verify load_config with the bundled default YAML returns a valid PARAConfig."""
        from pathlib import Path

        import file_organizer.methodologies.para.config as _mod
        from file_organizer.methodologies.para.config import PARAConfig, load_config

        default_yaml = Path(_mod.__file__).parent / "default_config.yaml"
        cfg = load_config(config_path=default_yaml)
        assert isinstance(cfg, PARAConfig)
        assert cfg.project_dir == "Projects"


# ---------------------------------------------------------------------------
# PARAFolderGenerator
# ---------------------------------------------------------------------------


class TestPARAFolderGenerator:
    """Tests for PARAFolderGenerator folder structure creation."""

    def test_dry_run_creates_no_files(self, tmp_path: Path) -> None:
        """Verify dry_run=True reports folders to create without writing to disk."""
        from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator

        gen = PARAFolderGenerator()
        result = gen.generate_structure(tmp_path, dry_run=True)

        assert result.success is True
        assert len(result.created_folders) >= 4  # 4 main PARA folders
        # No real folders were created in dry_run
        assert not (tmp_path / "Projects").exists()

    def test_real_creation_creates_folders(self, tmp_path: Path) -> None:
        """Verify generate_structure creates the four PARA directories on disk."""
        from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator

        gen = PARAFolderGenerator()
        result = gen.generate_structure(tmp_path, create_subdirs=False)

        assert result.success is True
        assert (tmp_path / "Projects").is_dir()
        assert (tmp_path / "Areas").is_dir()
        assert (tmp_path / "Resources").is_dir()
        assert (tmp_path / "Archive").is_dir()

    def test_with_subdirs_creates_more_folders(self, tmp_path: Path) -> None:
        """Verify create_subdirs=True produces more folders than create_subdirs=False."""
        from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator

        gen = PARAFolderGenerator()
        result_with = gen.generate_structure(tmp_path / "with", create_subdirs=True)
        result_without = gen.generate_structure(tmp_path / "without", create_subdirs=False)

        assert len(result_with.created_folders) > len(result_without.created_folders)

    def test_existing_folders_skipped(self, tmp_path: Path) -> None:
        """Verify a second generate_structure call skips already-existing folders."""
        from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator

        gen = PARAFolderGenerator()
        gen.generate_structure(tmp_path, create_subdirs=False)
        result2 = gen.generate_structure(tmp_path, create_subdirs=False)

        # All folders already exist — should all be skipped
        assert len(result2.skipped_folders) >= 4
        assert len(result2.created_folders) == 0

    def test_validate_structure_after_creation(self, tmp_path: Path) -> None:
        """Verify validate_structure returns True after a full structure is created."""
        from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator

        gen = PARAFolderGenerator()
        gen.generate_structure(tmp_path, create_subdirs=False)
        assert gen.validate_structure(tmp_path) is True

    def test_validate_structure_incomplete(self, tmp_path: Path) -> None:
        """Verify validate_structure returns False when some PARA dirs are missing."""
        from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator

        gen = PARAFolderGenerator()
        (tmp_path / "Projects").mkdir()
        # Missing Areas, Resources, Archive
        assert gen.validate_structure(tmp_path) is False

    def test_get_category_path(self, tmp_path: Path) -> None:
        """Verify get_category_path returns the expected subdirectory path."""
        from file_organizer.methodologies.para.categories import PARACategory
        from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator

        gen = PARAFolderGenerator()
        path = gen.get_category_path(PARACategory.PROJECT, root_path=tmp_path)
        assert path == tmp_path / "Projects"

    def test_create_category_folder(self, tmp_path: Path) -> None:
        """Verify create_category_folder creates the directory and returns it."""
        from file_organizer.methodologies.para.categories import PARACategory
        from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator

        gen = PARAFolderGenerator()
        created = gen.create_category_folder(PARACategory.RESOURCE, root_path=tmp_path)
        assert created.is_dir()
        assert created.name == "Resources"

    def test_create_category_folder_with_subfolder(self, tmp_path: Path) -> None:
        """Verify create_category_folder with subfolder creates a nested directory."""
        from file_organizer.methodologies.para.categories import PARACategory
        from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator

        gen = PARAFolderGenerator()
        created = gen.create_category_folder(
            PARACategory.PROJECT, subfolder="Work", root_path=tmp_path
        )
        assert created.is_dir()
        assert created.name == "Work"
        assert created.parent.name == "Projects"

    def test_no_root_and_no_default_raises(self) -> None:
        """Verify get_category_path raises ValueError when no root is available."""
        from file_organizer.methodologies.para.categories import PARACategory
        from file_organizer.methodologies.para.config import PARAConfig
        from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator

        cfg = PARAConfig()
        cfg.default_root = None
        gen = PARAFolderGenerator(config=cfg)
        with pytest.raises(ValueError, match="No root path"):
            gen.get_category_path(PARACategory.PROJECT)


# ---------------------------------------------------------------------------
# CategorizationResult
# ---------------------------------------------------------------------------


class TestCategorizationResult:
    """Tests for CategorizationResult data class."""

    def test_basic_result(self, tmp_path: Path) -> None:
        """Verify CategorizationResult stores category, confidence, and reasons."""
        from file_organizer.methodologies.para.categories import (
            CategorizationResult,
            PARACategory,
        )

        result = CategorizationResult(
            file_path=tmp_path / "doc.pdf",
            category=PARACategory.RESOURCE,
            confidence=0.85,
            reasons=["contains 'reference'", "static document"],
        )
        assert result.category == PARACategory.RESOURCE
        assert result.confidence == 0.85
        assert len(result.reasons) == 2

    def test_alternative_categories(self, tmp_path: Path) -> None:
        """Verify alternative_categories maps secondary categories to their scores."""
        from file_organizer.methodologies.para.categories import (
            CategorizationResult,
            PARACategory,
        )

        result = CategorizationResult(
            file_path=tmp_path / "f.txt",
            category=PARACategory.PROJECT,
            confidence=0.7,
            reasons=["deadline keyword"],
            alternative_categories={PARACategory.AREA: 0.3},
        )
        assert PARACategory.AREA in result.alternative_categories
        assert result.alternative_categories[PARACategory.AREA] == 0.3


# ---------------------------------------------------------------------------
# MigrationPlan and MigrationReport (data classes only)
# ---------------------------------------------------------------------------


class TestMigrationDataClasses:
    """Tests for migration-related data classes."""

    def test_migration_file(self, tmp_path: Path) -> None:
        """Verify MigrationFile stores target category, confidence, and reasoning."""
        from file_organizer.methodologies.para.categories import PARACategory
        from file_organizer.methodologies.para.migration_manager import MigrationFile

        mf = MigrationFile(
            source_path=tmp_path / "old.txt",
            target_category=PARACategory.ARCHIVE,
            target_path=tmp_path / "Archive" / "old.txt",
            confidence=0.9,
            reasoning=["inactive", "old"],
        )
        assert mf.target_category == PARACategory.ARCHIVE
        assert mf.confidence == 0.9
        assert len(mf.reasoning) == 2

    def test_migration_plan(self, tmp_path: Path) -> None:
        """Verify MigrationPlan stores total_count and per-category breakdown."""
        from datetime import UTC, datetime

        from file_organizer.methodologies.para.categories import PARACategory
        from file_organizer.methodologies.para.migration_manager import (
            MigrationFile,
            MigrationPlan,
        )

        files = [
            MigrationFile(
                source_path=tmp_path / "f.txt",
                target_category=PARACategory.ARCHIVE,
                target_path=tmp_path / "Archive" / "f.txt",
                confidence=0.8,
            )
        ]
        plan = MigrationPlan(
            files=files,
            total_count=1,
            by_category={PARACategory.ARCHIVE: 1},
            estimated_size=1024,
            created_at=datetime.now(UTC),
        )
        assert plan.total_count == 1
        assert plan.by_category[PARACategory.ARCHIVE] == 1

    def test_backup_metadata(self, tmp_path: Path) -> None:
        """Verify BackupMetadata stores backup ID, file count, status, and no restore time."""
        from datetime import UTC, datetime

        from file_organizer.methodologies.para.migration_manager import BackupMetadata

        meta = BackupMetadata(
            backup_id="bk-001",
            migration_id="mg-001",
            created_at=datetime.now(UTC),
            files_backed_up=5,
            total_size=2048,
            checksum="abc123",
            source_root=tmp_path,
            status="created",
        )
        assert meta.backup_id == "bk-001"
        assert meta.files_backed_up == 5
        assert meta.status == "created"
        assert meta.restored_at is None


# ---------------------------------------------------------------------------
# HeuristicWeights and CategoryThresholds
# ---------------------------------------------------------------------------


class TestHeuristicWeights:
    """Tests for HeuristicWeights dataclass."""

    def test_defaults_sum_to_one(self) -> None:
        """Verify default heuristic weights sum to exactly 1.0."""
        from file_organizer.methodologies.para.config import HeuristicWeights

        w = HeuristicWeights()
        total = w.temporal + w.content + w.structural + w.ai
        assert abs(total - 1.0) < 1e-9

    def test_custom_weights(self) -> None:
        """Verify custom weights are stored as specified."""
        from file_organizer.methodologies.para.config import HeuristicWeights

        w = HeuristicWeights(temporal=0.5, content=0.5, structural=0.0, ai=0.0)
        assert w.temporal == 0.5
        assert w.ai == 0.0


class TestCategoryThresholds:
    """Tests for CategoryThresholds dataclass."""

    def test_default_thresholds(self) -> None:
        """Verify all default category thresholds are in the valid [0, 1] range."""
        from file_organizer.methodologies.para.config import CategoryThresholds

        t = CategoryThresholds()
        assert 0.0 <= t.project <= 1.0
        assert 0.0 <= t.area <= 1.0
        assert 0.0 <= t.resource <= 1.0
        assert 0.0 <= t.archive <= 1.0
