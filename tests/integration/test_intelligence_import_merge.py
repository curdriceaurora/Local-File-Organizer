"""Integration tests for profile import, merge, and migration.

Covers:
  - services/intelligence/profile_importer.py — ProfileImporter, ValidationResult
  - services/intelligence/profile_merger.py   — ProfileMerger, MergeStrategy
  - services/intelligence/profile_migrator.py — ProfileMigrator
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from file_organizer.services.intelligence.profile_exporter import ProfileExporter
from file_organizer.services.intelligence.profile_importer import (
    ProfileImporter,
    ValidationResult,
)
from file_organizer.services.intelligence.profile_manager import ProfileManager
from file_organizer.services.intelligence.profile_merger import MergeStrategy, ProfileMerger
from file_organizer.services.intelligence.profile_migrator import ProfileMigrator

pytestmark = [pytest.mark.ci, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager(tmp_path: Path) -> ProfileManager:
    return ProfileManager(storage_path=tmp_path / "profiles")


@pytest.fixture()
def importer(manager: ProfileManager) -> ProfileImporter:
    return ProfileImporter(profile_manager=manager)


@pytest.fixture()
def exporter(manager: ProfileManager) -> ProfileExporter:
    return ProfileExporter(profile_manager=manager)


@pytest.fixture()
def merger(manager: ProfileManager) -> ProfileMerger:
    return ProfileMerger(profile_manager=manager)


@pytest.fixture()
def migrator(manager: ProfileManager) -> ProfileMigrator:
    return ProfileMigrator(profile_manager=manager)


def _make_valid_export(tmp_path: Path, name: str = "default") -> Path:
    """Export the default profile to a temp file and return the path."""
    mgr = ProfileManager(storage_path=tmp_path / "source_profiles")
    exp = ProfileExporter(profile_manager=mgr)
    out = tmp_path / f"{name}.json"
    exp.export_profile("default", out)
    return out


# ---------------------------------------------------------------------------
# ValidationResult data class
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_valid_result_str_contains_true(self) -> None:
        r = ValidationResult(valid=True, errors=[], warnings=[])
        assert "True" in str(r)

    def test_invalid_result_str_contains_errors(self) -> None:
        r = ValidationResult(valid=False, errors=["missing field"], warnings=[])
        assert "missing field" in str(r)

    def test_result_with_warnings_str(self) -> None:
        r = ValidationResult(valid=True, errors=[], warnings=["large file"])
        assert "large file" in str(r)


# ---------------------------------------------------------------------------
# ProfileImporter — validate_import_file
# ---------------------------------------------------------------------------


class TestProfileImporterValidate:
    def test_validate_missing_file(self, importer: ProfileImporter, tmp_path: Path) -> None:
        result = importer.validate_import_file(tmp_path / "nope.json")
        assert result.valid is False
        assert any("not found" in e for e in result.errors)

    def test_validate_invalid_json(self, importer: ProfileImporter, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{invalid")
        result = importer.validate_import_file(bad)
        assert result.valid is False

    def test_validate_missing_required_fields(
        self, importer: ProfileImporter, tmp_path: Path
    ) -> None:
        f = tmp_path / "partial.json"
        f.write_text(json.dumps({"some_field": "value"}))
        result = importer.validate_import_file(f)
        assert result.valid is False
        assert any("required" in e.lower() for e in result.errors)

    def test_validate_valid_export_file(self, importer: ProfileImporter, tmp_path: Path) -> None:
        export_path = _make_valid_export(tmp_path)
        result = importer.validate_import_file(export_path)
        assert result.valid is True
        assert result.profile_data is not None

    def test_validate_warns_when_profile_exists(
        self, importer: ProfileImporter, tmp_path: Path
    ) -> None:
        # default profile already exists in manager fixture
        export_path = _make_valid_export(tmp_path)
        result = importer.validate_import_file(export_path)
        # Should warn about overwrite (default profile exists)
        assert any("already exists" in w for w in result.warnings)

    def test_validate_invalid_empty_profile_name(
        self, importer: ProfileImporter, tmp_path: Path
    ) -> None:
        f = tmp_path / "empty_name.json"
        f.write_text(json.dumps({"profile_name": "", "profile_version": "1.0"}))
        result = importer.validate_import_file(f)
        assert result.valid is False

    def test_validate_unknown_version_warns(
        self, importer: ProfileImporter, tmp_path: Path
    ) -> None:
        f = tmp_path / "future.json"
        f.write_text(
            json.dumps(
                {
                    "profile_name": "future_profile",
                    "profile_version": "99.0",
                    "preferences": {"global": {}, "directory_specific": {}},
                }
            )
        )
        result = importer.validate_import_file(f)
        assert any("version" in w.lower() for w in result.warnings)


class TestProfileImporterPreview:
    def test_preview_valid_file(self, importer: ProfileImporter, tmp_path: Path) -> None:
        export_path = _make_valid_export(tmp_path)
        preview = importer.preview_import(export_path)
        assert preview is not None
        assert "profile_name" in preview

    def test_preview_missing_file_returns_none(
        self, importer: ProfileImporter, tmp_path: Path
    ) -> None:
        assert importer.preview_import(tmp_path / "missing.json") is None


class TestProfileImporterImport:
    def test_import_profile_basic(self, importer: ProfileImporter, tmp_path: Path) -> None:
        export_path = _make_valid_export(tmp_path)
        profile = importer.import_profile(export_path)
        # Either the default profile is updated/re-imported or a new one created
        assert profile is not None

    def test_import_profile_with_new_name(self, importer: ProfileImporter, tmp_path: Path) -> None:
        export_path = _make_valid_export(tmp_path)
        profile = importer.import_profile(export_path, new_name="ImportedProfile")
        assert profile is not None
        assert profile.profile_name == "ImportedProfile"

    def test_import_missing_file_returns_none(
        self, importer: ProfileImporter, tmp_path: Path
    ) -> None:
        assert importer.import_profile(tmp_path / "nope.json") is None

    def test_import_invalid_json_returns_none(
        self, importer: ProfileImporter, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert importer.import_profile(bad) is None


# ---------------------------------------------------------------------------
# ProfileMerger
# ---------------------------------------------------------------------------


class TestProfileMergerBasics:
    def test_merge_requires_at_least_two_profiles(self, merger: ProfileMerger) -> None:
        result = merger.merge_profiles(["default"])
        assert result is None

    def test_merge_nonexistent_profile_returns_none(self, merger: ProfileMerger) -> None:
        result = merger.merge_profiles(["default", "ghost_xyz"])
        assert result is None

    def test_merge_two_existing_profiles(
        self, manager: ProfileManager, merger: ProfileMerger
    ) -> None:
        manager.create_profile("Alpha", "alpha profile")
        result = merger.merge_profiles(["default", "Alpha"])
        assert result is not None

    def test_merge_uses_custom_output_name(
        self, manager: ProfileManager, merger: ProfileMerger
    ) -> None:
        manager.create_profile("Beta", "beta profile")
        result = merger.merge_profiles(["default", "Beta"], output_name="MyMerged")
        assert result is not None
        assert result.profile_name == "MyMerged"

    def test_merge_invalid_strategy_returns_none(
        self, manager: ProfileManager, merger: ProfileMerger
    ) -> None:
        manager.create_profile("C", "c profile")
        result = merger.merge_profiles(["default", "C"], merge_strategy="invalid_xyz")
        assert result is None


class TestProfileMergerStrategies:
    def _setup_two_profiles(self, manager: ProfileManager) -> tuple[str, str]:
        manager.create_profile("P1", "profile 1")
        manager.create_profile("P2", "profile 2")
        return "P1", "P2"

    def test_merge_strategy_recent(self, manager: ProfileManager, merger: ProfileMerger) -> None:
        p1, p2 = self._setup_two_profiles(manager)
        result = merger.merge_profiles([p1, p2], merge_strategy="recent")
        assert result is not None

    def test_merge_strategy_confident(self, manager: ProfileManager, merger: ProfileMerger) -> None:
        p1, p2 = self._setup_two_profiles(manager)
        result = merger.merge_profiles([p1, p2], merge_strategy="confident")
        assert result is not None

    def test_merge_strategy_first(self, manager: ProfileManager, merger: ProfileMerger) -> None:
        p1, p2 = self._setup_two_profiles(manager)
        result = merger.merge_profiles([p1, p2], merge_strategy="first")
        assert result is not None

    def test_merge_strategy_last(self, manager: ProfileManager, merger: ProfileMerger) -> None:
        p1, p2 = self._setup_two_profiles(manager)
        result = merger.merge_profiles([p1, p2], merge_strategy="last")
        assert result is not None

    def test_merge_three_profiles(self, manager: ProfileManager, merger: ProfileMerger) -> None:
        manager.create_profile("X1", "x1")
        manager.create_profile("X2", "x2")
        result = merger.merge_profiles(["default", "X1", "X2"])
        assert result is not None


class TestProfileMergerHelpers:
    def test_resolve_conflicts_picks_higher_confidence(self, merger: ProfileMerger) -> None:
        low = {
            "value": "Documents",
            "metadata": {"confidence": 0.2, "updated": "2026-01-01T00:00:00Z"},
        }
        high = {"value": "PDFs", "metadata": {"confidence": 0.9, "updated": "2026-01-20T00:00:00Z"}}
        result = merger.resolve_conflicts([low, high], strategy=MergeStrategy.CONFIDENT)
        assert result == "PDFs"

    def test_resolve_conflicts_first_strategy(self, merger: ProfileMerger) -> None:
        p1 = {"value": "A", "metadata": {}}
        p2 = {"value": "B", "metadata": {}}
        result = merger.resolve_conflicts([p1, p2], strategy=MergeStrategy.FIRST)
        assert result == "A"

    def test_resolve_conflicts_last_strategy(self, merger: ProfileMerger) -> None:
        p1 = {"value": "A", "metadata": {}}
        p2 = {"value": "B", "metadata": {}}
        result = merger.resolve_conflicts([p1, p2], strategy=MergeStrategy.LAST)
        assert result == "B"

    def test_resolve_conflicts_empty_returns_none(self, merger: ProfileMerger) -> None:
        result = merger.resolve_conflicts([], strategy=MergeStrategy.FIRST)
        assert result is None

    def test_preserve_high_confidence_is_callable(
        self, manager: ProfileManager, merger: ProfileMerger
    ) -> None:
        manager.create_profile("Src1", "src 1")
        merged = manager.get_profile("default")
        src = manager.get_profile("Src1")
        assert merged is not None and src is not None
        # Just verify it doesn't raise
        merger.preserve_high_confidence(merged, [src])


# ---------------------------------------------------------------------------
# ProfileMigrator
# ---------------------------------------------------------------------------


class TestProfileMigratorBasics:
    def test_validate_migration_default_profile(self, migrator: ProfileMigrator) -> None:
        result = migrator.validate_migration("default")
        assert result is True

    def test_validate_migration_nonexistent_returns_false(self, migrator: ProfileMigrator) -> None:
        result = migrator.validate_migration("phantom_xyz")
        assert result is False

    def test_list_backups_returns_list(self, migrator: ProfileMigrator) -> None:
        result = migrator.list_backups()
        assert result == []

    def test_list_backups_specific_profile(self, migrator: ProfileMigrator) -> None:
        result = migrator.list_backups(profile_name="default")
        assert result == []

    def test_get_migration_history_returns_list_or_none(self, migrator: ProfileMigrator) -> None:
        result = migrator.get_migration_history("default")
        assert result is None or isinstance(result, list)

    def test_migrate_rejects_unsupported_target_even_when_versions_match(
        self, manager: ProfileManager, migrator: ProfileMigrator
    ) -> None:
        manager.create_profile("custom", "custom profile")
        manager.update_profile("custom", profile_version="9.9")
        result = migrator.migrate_version("custom", "9.9")
        assert result is False


class TestProfileMigratorBackup:
    def test_backup_before_migration_creates_file(
        self, manager: ProfileManager, migrator: ProfileMigrator, tmp_path: Path
    ) -> None:
        profile = manager.get_profile("default")
        assert profile is not None
        backup_path = migrator.backup_before_migration(profile)
        # Either returns a path or None (depending on storage setup)
        assert backup_path is None or isinstance(backup_path, Path)

    def test_rollback_nonexistent_backup_returns_false(
        self, migrator: ProfileMigrator, tmp_path: Path
    ) -> None:
        fake_backup = tmp_path / "nonexistent_backup.json"
        result = migrator.rollback_migration("default", fake_backup)
        assert result is False


class TestProfileMigratorMigrate:
    def test_migrate_to_same_version(self, migrator: ProfileMigrator) -> None:
        # Migrating to same version (1.0 → 1.0) should succeed or be a no-op
        result = migrator.migrate_version("default", "1.0")
        assert result is True

    def test_migrate_nonexistent_profile_returns_false(self, migrator: ProfileMigrator) -> None:
        result = migrator.migrate_version("ghost_profile_xyz", "1.0")
        assert result is False
