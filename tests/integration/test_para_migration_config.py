"""Integration tests for PARA methodology migration and config.

Covers:
  - methodologies/para/migration_manager.py  — PARAMigrationManager, MigrationPlan, MigrationFile, MigrationReport
  - methodologies/para/config.py             — PARAConfig
  - methodologies/para/categories.py         — CategorizationResult, CategoryDefinition, PARACategory
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.methodologies.para.categories import (
    CategorizationResult,
    CategoryDefinition,
    PARACategory,
)
from file_organizer.methodologies.para.config import PARAConfig
from file_organizer.methodologies.para.migration_manager import (
    MigrationFile,
    MigrationPlan,
    MigrationReport,
    PARAMigrationManager,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# PARACategory enum
# ---------------------------------------------------------------------------


class TestPARACategory:
    def test_project_value(self) -> None:
        assert PARACategory.PROJECT.value == "project"

    def test_area_value(self) -> None:
        assert PARACategory.AREA.value == "area"

    def test_resource_value(self) -> None:
        assert PARACategory.RESOURCE.value == "resource"

    def test_archive_value(self) -> None:
        assert PARACategory.ARCHIVE.value == "archive"

    def test_four_categories(self) -> None:
        assert len(list(PARACategory)) == 4


# ---------------------------------------------------------------------------
# CategoryDefinition
# ---------------------------------------------------------------------------


class TestCategoryDefinition:
    def test_created(self) -> None:
        cd = CategoryDefinition(
            name=PARACategory.PROJECT,
            description="Active projects",
            criteria=["has deadline", "active work"],
            examples=["website redesign", "book"],
            keywords=["project", "deadline"],
            patterns=["*.md"],
        )
        assert cd.name == PARACategory.PROJECT
        assert cd.description == "Active projects"

    def _make_def(self, name: PARACategory = PARACategory.AREA, **kwargs) -> CategoryDefinition:
        defaults = {
            "description": "Some area",
            "criteria": ["has ongoing maintenance"],
            "examples": ["Health", "Finance"],
            "keywords": ["area", "responsibility"],
            "patterns": ["*"],
        }
        defaults.update(kwargs)
        return CategoryDefinition(name=name, **defaults)

    def test_default_threshold(self) -> None:
        cd = self._make_def(PARACategory.AREA)
        assert cd.confidence_threshold == 0.75

    def test_custom_threshold(self) -> None:
        cd = self._make_def(PARACategory.RESOURCE, confidence_threshold=0.6)
        assert cd.confidence_threshold == 0.6

    def test_auto_categorize_default(self) -> None:
        cd = self._make_def(PARACategory.ARCHIVE)
        assert cd.auto_categorize is True


# ---------------------------------------------------------------------------
# CategorizationResult
# ---------------------------------------------------------------------------


class TestCategorizationResult:
    def test_created(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"x")
        result = CategorizationResult(
            file_path=f,
            category=PARACategory.RESOURCE,
            confidence=0.85,
            reasons=["keyword match", "extension match"],
        )
        assert result.category == PARACategory.RESOURCE
        assert result.confidence == 0.85

    def test_reasons_stored(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        result = CategorizationResult(
            file_path=f,
            category=PARACategory.ARCHIVE,
            confidence=0.7,
            reasons=["old file"],
        )
        assert "old file" in result.reasons

    def test_default_alternative_categories(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("x")
        result = CategorizationResult(
            file_path=f,
            category=PARACategory.PROJECT,
            confidence=0.9,
            reasons=["keyword"],
        )
        assert result.alternative_categories == {}

    def test_alternative_categories_set(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("x")
        result = CategorizationResult(
            file_path=f,
            category=PARACategory.PROJECT,
            confidence=0.9,
            reasons=["keyword"],
            alternative_categories={PARACategory.AREA: 0.3},
        )
        assert PARACategory.AREA in result.alternative_categories


# ---------------------------------------------------------------------------
# PARAConfig
# ---------------------------------------------------------------------------


class TestPARAConfigInit:
    def test_default_init(self) -> None:
        config = PARAConfig()
        assert config is not None

    def test_default_dirs(self) -> None:
        config = PARAConfig()
        assert config.project_dir == "Projects"
        assert config.area_dir == "Areas"
        assert config.resource_dir == "Resources"
        assert config.archive_dir == "Archive"

    def test_custom_dirs(self) -> None:
        config = PARAConfig(project_dir="P", area_dir="A", resource_dir="R", archive_dir="Arch")
        assert config.project_dir == "P"

    def test_heuristics_enabled_by_default(self) -> None:
        config = PARAConfig()
        assert config.enable_temporal_heuristic is True
        assert config.enable_content_heuristic is True
        assert config.enable_structural_heuristic is True

    def test_ai_disabled_by_default(self) -> None:
        config = PARAConfig()
        assert config.enable_ai_heuristic is False


class TestPARAConfigGetters:
    def test_get_category_directory_project(self) -> None:
        config = PARAConfig()
        d = config.get_category_directory(PARACategory.PROJECT)
        assert isinstance(d, str)
        assert d == "Projects"

    def test_get_category_directory_archive(self) -> None:
        config = PARAConfig()
        d = config.get_category_directory(PARACategory.ARCHIVE)
        assert d == "Archive"

    def test_get_category_threshold_returns_float(self) -> None:
        config = PARAConfig()
        t = config.get_category_threshold(PARACategory.PROJECT)
        assert isinstance(t, float)
        assert 0.0 <= t <= 1.0

    def test_get_category_keywords_returns_list(self) -> None:
        config = PARAConfig()
        kw = config.get_category_keywords(PARACategory.RESOURCE)
        assert len(kw) >= 1


class TestPARAConfigSaveLoad:
    def test_save_to_yaml(self, tmp_path: Path) -> None:
        config = PARAConfig()
        yaml_path = tmp_path / "para_config.yaml"
        config.save_to_yaml(yaml_path)
        assert yaml_path.exists()

    def test_load_from_yaml_returns_config(self, tmp_path: Path) -> None:
        config = PARAConfig()
        yaml_path = tmp_path / "config.yaml"
        config.save_to_yaml(yaml_path)
        loaded = PARAConfig.load_from_yaml(yaml_path)
        assert isinstance(loaded, PARAConfig)


# ---------------------------------------------------------------------------
# MigrationFile, MigrationPlan, MigrationReport dataclasses
# ---------------------------------------------------------------------------


class TestMigrationFile:
    def test_created(self, tmp_path: Path) -> None:
        src = tmp_path / "file.txt"
        tgt = tmp_path / "Projects" / "file.txt"
        mf = MigrationFile(
            source_path=src,
            target_category=PARACategory.PROJECT,
            target_path=tgt,
            confidence=0.8,
        )
        assert mf.source_path == src
        assert mf.target_category == PARACategory.PROJECT
        assert mf.confidence == 0.8

    def test_reasoning_default_empty(self, tmp_path: Path) -> None:
        mf = MigrationFile(
            source_path=tmp_path / "f.txt",
            target_category=PARACategory.AREA,
            target_path=tmp_path / "Areas" / "f.txt",
            confidence=0.6,
        )
        assert mf.reasoning == []

    def test_custom_reasoning(self, tmp_path: Path) -> None:
        mf = MigrationFile(
            source_path=tmp_path / "f.txt",
            target_category=PARACategory.RESOURCE,
            target_path=tmp_path / "Resources" / "f.txt",
            confidence=0.9,
            reasoning=["keyword match"],
        )
        assert "keyword match" in mf.reasoning


class TestMigrationPlan:
    def test_created(self) -> None:
        plan = MigrationPlan(
            files=[],
            total_count=0,
            by_category={},
            estimated_size=0,
            created_at=datetime.now(UTC),
        )
        assert isinstance(plan.files, list)
        assert plan.total_count == 0

    def test_by_category_stored(self) -> None:
        plan = MigrationPlan(
            files=[],
            total_count=5,
            by_category={PARACategory.PROJECT: 3, PARACategory.ARCHIVE: 2},
            estimated_size=1024,
            created_at=datetime.now(UTC),
        )
        assert plan.by_category[PARACategory.PROJECT] == 3


class TestMigrationReport:
    def test_created(self) -> None:
        plan = MigrationPlan(
            files=[], total_count=0, by_category={}, estimated_size=0, created_at=datetime.now(UTC)
        )
        report = MigrationReport(
            plan=plan,
            migrated=[],
            failed=[],
            skipped=[],
            duration_seconds=1.5,
            success=True,
        )
        assert report.success is True
        assert report.duration_seconds == 1.5

    def test_failed_list(self) -> None:
        plan = MigrationPlan(
            files=[], total_count=0, by_category={}, estimated_size=0, created_at=datetime.now(UTC)
        )
        report = MigrationReport(
            plan=plan,
            migrated=[],
            failed=[],
            skipped=[],
            duration_seconds=0.5,
            success=False,
        )
        assert isinstance(report.failed, list)
        assert report.success is False


# ---------------------------------------------------------------------------
# PARAMigrationManager
# ---------------------------------------------------------------------------


@pytest.fixture()
def migration_manager() -> PARAMigrationManager:
    return PARAMigrationManager()


class TestPARAMigrationManagerInit:
    def test_default_init(self) -> None:
        m = PARAMigrationManager()
        assert m is not None

    def test_with_config(self) -> None:
        config = PARAConfig()
        m = PARAMigrationManager(config=config)
        assert m is not None


class TestAnalyzeSource:
    def test_empty_dir_returns_plan(
        self, migration_manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        source = tmp_path / "source"
        source.mkdir()
        target = tmp_path / "target"
        plan = migration_manager.analyze_source(source, target)
        assert isinstance(plan, MigrationPlan)

    def test_plan_has_correct_structure(
        self, migration_manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        source = tmp_path / "source"
        source.mkdir()
        target = tmp_path / "target"
        plan = migration_manager.analyze_source(source, target)
        assert plan.files == []
        assert plan.total_count == 0
        assert plan.by_category == {}

    def test_with_files(self, migration_manager: PARAMigrationManager, tmp_path: Path) -> None:
        source = tmp_path / "source"
        source.mkdir()
        (source / "report.pdf").write_bytes(b"pdf")
        (source / "notes.txt").write_text("notes")
        target = tmp_path / "target"
        plan = migration_manager.analyze_source(source, target)
        assert isinstance(plan, MigrationPlan)
        assert plan.total_count >= 0

    def test_plan_total_count_matches_files(
        self, migration_manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        source = tmp_path / "source"
        source.mkdir()
        for i in range(3):
            (source / f"doc{i}.txt").write_text(f"content {i}")
        target = tmp_path / "target"
        plan = migration_manager.analyze_source(source, target)
        assert plan.total_count == len(plan.files)


class TestGeneratePreview:
    def test_empty_plan_returns_string(self, migration_manager: PARAMigrationManager) -> None:
        plan = MigrationPlan(
            files=[], total_count=0, by_category={}, estimated_size=0, created_at=datetime.now(UTC)
        )
        preview = migration_manager.generate_preview(plan)
        assert len(preview) > 0

    def test_preview_with_files(
        self, migration_manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        mf = MigrationFile(
            source_path=tmp_path / "file.txt",
            target_category=PARACategory.PROJECT,
            target_path=tmp_path / "Projects" / "file.txt",
            confidence=0.8,
        )
        plan = MigrationPlan(
            files=[mf],
            total_count=1,
            by_category={PARACategory.PROJECT: 1},
            estimated_size=100,
            created_at=datetime.now(UTC),
        )
        preview = migration_manager.generate_preview(plan)
        assert isinstance(preview, str)
        assert len(preview) > 0


class TestExecuteMigrationDryRun:
    def test_dry_run_does_not_move_files(
        self, migration_manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        source = tmp_path / "source"
        source.mkdir()
        f = source / "doc.txt"
        f.write_text("content")
        target = tmp_path / "target"
        plan = migration_manager.analyze_source(source, target)
        report = migration_manager.execute_migration(plan, dry_run=True, create_backup=False)
        assert isinstance(report, MigrationReport)
        # Files should still exist in source after dry run
        assert f.exists()

    def test_dry_run_returns_report(
        self, migration_manager: PARAMigrationManager, tmp_path: Path
    ) -> None:
        plan = MigrationPlan(
            files=[], total_count=0, by_category={}, estimated_size=0, created_at=datetime.now(UTC)
        )
        report = migration_manager.execute_migration(plan, dry_run=True, create_backup=False)
        assert isinstance(report, MigrationReport)


class TestListBackups:
    def test_empty_returns_list(self, migration_manager: PARAMigrationManager) -> None:
        backups = migration_manager.list_backups()
        assert backups == []
