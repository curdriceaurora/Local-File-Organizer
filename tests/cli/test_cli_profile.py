"""Tests for file_organizer.cli.profile module.

Tests the Click-based profile management CLI commands including:
- Profile CRUD operations (list, create, activate, delete, current)
- Import/Export functionality
- Profile merging
- Template management
- Migration operations
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from file_organizer.cli.profile import profile_command

pytestmark = [pytest.mark.unit]


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_profile():
    """Create a mock profile object."""
    profile = MagicMock()
    profile.profile_name = "test-profile"
    profile.description = "Test description"
    profile.created = "2026-01-01T00:00:00Z"
    profile.updated = "2026-01-01T00:00:00Z"
    profile.profile_version = "1.0"
    profile.preferences = {"global": {"key1": "val1"}, "directory_specific": {}}
    profile.learned_patterns = ["pattern1"]
    profile.confidence_data = {"category": 0.9}
    return profile


@pytest.fixture
def mock_manager(mock_profile):
    """Create a mock ProfileManager."""
    mgr = MagicMock()
    mgr.list_profiles.return_value = [mock_profile]
    mgr._get_active_profile_name.return_value = "test-profile"
    mgr.get_active_profile.return_value = mock_profile
    mgr.create_profile.return_value = mock_profile
    mgr.activate_profile.return_value = True
    mgr.delete_profile.return_value = True
    return mgr


# ============================================================================
# Profile CRUD Tests
# ============================================================================


@pytest.mark.unit
class TestListProfiles:
    """Tests for the 'list' subcommand."""

    def test_list_profiles_success(self, runner, mock_manager):
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["list"])
        assert result.exit_code == 0
        assert "test-profile" in result.output
        assert "[ACTIVE]" in result.output
        assert "1 total" in result.output

    def test_list_profiles_empty(self, runner, mock_manager):
        mock_manager.list_profiles.return_value = []
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["list"])
        assert result.exit_code == 0
        assert "No profiles found" in result.output

    def test_list_profiles_no_active(self, runner, mock_manager, mock_profile):
        mock_manager._get_active_profile_name.return_value = "other-profile"
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["list"])
        assert result.exit_code == 0
        assert "[ACTIVE]" not in result.output

    def test_list_profiles_error(self, runner, mock_manager):
        mock_manager.list_profiles.side_effect = RuntimeError("DB error")
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["list"])
        assert result.exit_code != 0
        assert "Error listing profiles" in result.output

    def test_list_profiles_shows_preferences_counts(self, runner, mock_manager):
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["list"])
        assert "1 global" in result.output
        assert "0 directory-specific" in result.output


@pytest.mark.unit
class TestCreateProfile:
    """Tests for the 'create' subcommand."""

    def test_create_profile_success(self, runner, mock_manager):
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["create", "new-profile"])
        assert result.exit_code == 0
        assert "Created profile: new-profile" in result.output

    def test_create_profile_with_description(self, runner, mock_manager):
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(
                profile_command, ["create", "new-profile", "-d", "My description"]
            )
        assert result.exit_code == 0
        mock_manager.create_profile.assert_called_once_with("new-profile", "My description")

    def test_create_profile_with_activate(self, runner, mock_manager):
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["create", "new-profile", "--activate"])
        assert result.exit_code == 0
        assert "Activated profile: new-profile" in result.output
        mock_manager.activate_profile.assert_called_once_with("new-profile")

    def test_create_profile_failure(self, runner, mock_manager):
        mock_manager.create_profile.return_value = None
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["create", "bad-profile"])
        assert result.exit_code != 0
        assert "Failed to create profile" in result.output

    def test_create_profile_activate_failure(self, runner, mock_manager):
        mock_manager.activate_profile.return_value = False
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["create", "new-profile", "-a"])
        assert "Failed to activate profile" in result.output

    def test_create_profile_error(self, runner, mock_manager):
        mock_manager.create_profile.side_effect = RuntimeError("fail")
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["create", "bad"])
        assert result.exit_code != 0
        assert "Error creating profile" in result.output


@pytest.mark.unit
class TestActivateProfile:
    """Tests for the 'activate' subcommand."""

    def test_activate_success(self, runner, mock_manager):
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["activate", "my-profile"])
        assert result.exit_code == 0
        assert "Activated profile: my-profile" in result.output

    def test_activate_failure(self, runner, mock_manager):
        mock_manager.activate_profile.return_value = False
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["activate", "bad"])
        assert result.exit_code != 0
        assert "Failed to activate" in result.output

    def test_activate_error(self, runner, mock_manager):
        mock_manager.activate_profile.side_effect = RuntimeError("fail")
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["activate", "err"])
        assert result.exit_code != 0
        assert "Error activating" in result.output


@pytest.mark.unit
class TestDeleteProfile:
    """Tests for the 'delete' subcommand."""

    def test_delete_with_force(self, runner, mock_manager):
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["delete", "old", "--force"])
        assert result.exit_code == 0
        assert "Deleted profile: old" in result.output

    def test_delete_with_confirmation_yes(self, runner, mock_manager):
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["delete", "old"], input="y\n")
        assert result.exit_code == 0
        assert "Deleted profile: old" in result.output

    def test_delete_with_confirmation_no(self, runner, mock_manager):
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["delete", "old"], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled" in result.output

    def test_delete_failure(self, runner, mock_manager):
        mock_manager.delete_profile.return_value = False
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["delete", "bad", "-f"])
        assert result.exit_code != 0
        assert "Failed to delete" in result.output


@pytest.mark.unit
class TestShowCurrent:
    """Tests for the 'current' subcommand."""

    def test_show_current_success(self, runner, mock_manager, mock_profile):
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["current"])
        assert result.exit_code == 0
        assert "Active Profile: test-profile" in result.output
        assert "Version: 1.0" in result.output
        assert "Learned patterns: 1" in result.output

    def test_show_current_no_active(self, runner, mock_manager):
        mock_manager.get_active_profile.return_value = None
        with patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager):
            result = runner.invoke(profile_command, ["current"])
        assert result.exit_code != 0
        assert "No active profile" in result.output


# ============================================================================
# Export/Import Tests
# ============================================================================


@pytest.mark.unit
class TestExportProfile:
    """Tests for the 'export' subcommand."""

    def test_export_success(self, runner, mock_manager, tmp_path):
        output_file = str(tmp_path / "exported.json")
        mock_exporter = MagicMock()
        mock_exporter.export_profile.return_value = True
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileExporter", return_value=mock_exporter),
        ):
            result = runner.invoke(
                profile_command, ["export", "test-profile", "-o", output_file]
            )
        assert result.exit_code == 0
        assert "Exported profile" in result.output

    def test_export_selective(self, runner, mock_manager, tmp_path):
        output_file = str(tmp_path / "exported.json")
        mock_exporter = MagicMock()
        mock_exporter.export_selective.return_value = True
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileExporter", return_value=mock_exporter),
        ):
            result = runner.invoke(
                profile_command,
                ["export", "test-profile", "-o", output_file, "-s", "naming", "-s", "folders"],
            )
        assert result.exit_code == 0
        mock_exporter.export_selective.assert_called_once()

    def test_export_failure(self, runner, mock_manager, tmp_path):
        output_file = str(tmp_path / "bad.json")
        mock_exporter = MagicMock()
        mock_exporter.export_profile.return_value = False
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileExporter", return_value=mock_exporter),
        ):
            result = runner.invoke(
                profile_command, ["export", "test-profile", "-o", output_file]
            )
        assert result.exit_code != 0
        assert "Failed to export" in result.output


@pytest.mark.unit
class TestImportProfile:
    """Tests for the 'import' subcommand."""

    def test_import_success(self, runner, mock_manager, mock_profile, tmp_path):
        import_file = tmp_path / "import.json"
        import_file.write_text('{"profile_name": "imported"}')

        mock_importer = MagicMock()
        mock_importer.import_profile.return_value = mock_profile
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileImporter", return_value=mock_importer),
        ):
            result = runner.invoke(profile_command, ["import", str(import_file)])
        assert result.exit_code == 0
        assert "Imported profile" in result.output

    def test_import_with_new_name(self, runner, mock_manager, mock_profile, tmp_path):
        import_file = tmp_path / "import.json"
        import_file.write_text('{"profile_name": "original"}')

        mock_importer = MagicMock()
        mock_importer.import_profile.return_value = mock_profile
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileImporter", return_value=mock_importer),
        ):
            result = runner.invoke(
                profile_command, ["import", str(import_file), "--as", "new-name"]
            )
        assert result.exit_code == 0
        mock_importer.import_profile.assert_called_once_with(Path(str(import_file)), "new-name")

    def test_import_preview(self, runner, mock_manager, tmp_path):
        import_file = tmp_path / "import.json"
        import_file.write_text('{"profile_name": "preview-test"}')

        mock_importer = MagicMock()
        mock_importer.preview_import.return_value = {
            "profile_name": "preview-test",
            "description": "desc",
            "profile_version": "1.0",
            "export_type": "full",
            "preferences_count": {"global": 5},
            "learned_patterns_count": 3,
            "confidence_data_count": 2,
            "validation": {"valid": True, "errors": [], "warnings": ["warn1"]},
        }
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileImporter", return_value=mock_importer),
        ):
            result = runner.invoke(
                profile_command, ["import", str(import_file), "--preview"]
            )
        assert result.exit_code == 0
        assert "Import Preview" in result.output
        assert "preview-test" in result.output
        assert "warn1" in result.output

    def test_import_preview_with_conflicts(self, runner, mock_manager, tmp_path):
        import_file = tmp_path / "import.json"
        import_file.write_text('{"data": true}')

        mock_importer = MagicMock()
        mock_importer.preview_import.return_value = {
            "profile_name": "p",
            "description": "d",
            "profile_version": "1.0",
            "export_type": "full",
            "learned_patterns_count": 0,
            "confidence_data_count": 0,
            "validation": {"valid": True, "errors": [], "warnings": []},
            "conflicts": {"message": "Profile already exists"},
        }
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileImporter", return_value=mock_importer),
        ):
            result = runner.invoke(
                profile_command, ["import", str(import_file), "--preview"]
            )
        assert result.exit_code == 0
        assert "Conflicts detected" in result.output

    def test_import_failure(self, runner, mock_manager, tmp_path):
        import_file = tmp_path / "import.json"
        import_file.write_text('{}')

        mock_importer = MagicMock()
        mock_importer.import_profile.return_value = None
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileImporter", return_value=mock_importer),
        ):
            result = runner.invoke(profile_command, ["import", str(import_file)])
        assert result.exit_code != 0
        assert "Failed to import" in result.output


# ============================================================================
# Merge Tests
# ============================================================================


@pytest.mark.unit
class TestMergeProfiles:
    """Tests for the 'merge' subcommand."""

    def test_merge_success(self, runner, mock_manager, mock_profile):
        mock_merger = MagicMock()
        mock_merger.merge_profiles.return_value = mock_profile
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMerger", return_value=mock_merger),
        ):
            result = runner.invoke(
                profile_command, ["merge", "p1", "p2", "-o", "merged"]
            )
        assert result.exit_code == 0
        assert "Merged 2 profiles" in result.output

    def test_merge_too_few_profiles(self, runner, mock_manager):
        mock_merger = MagicMock()
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMerger", return_value=mock_merger),
        ):
            result = runner.invoke(
                profile_command, ["merge", "p1", "-o", "merged"]
            )
        assert result.exit_code != 0
        assert "Need at least 2 profiles" in result.output

    def test_merge_with_show_conflicts_and_confirm(self, runner, mock_manager, mock_profile):
        mock_merger = MagicMock()
        mock_merger.get_merge_conflicts.return_value = {"naming": ["val1", "val2"]}
        mock_merger.merge_profiles.return_value = mock_profile
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMerger", return_value=mock_merger),
        ):
            result = runner.invoke(
                profile_command,
                ["merge", "p1", "p2", "-o", "merged", "--show-conflicts"],
                input="y\n",
            )
        assert result.exit_code == 0
        assert "Conflicts detected" in result.output
        assert "Merged 2 profiles" in result.output

    def test_merge_with_show_conflicts_cancel(self, runner, mock_manager):
        mock_merger = MagicMock()
        mock_merger.get_merge_conflicts.return_value = {"naming": ["val1", "val2"]}
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMerger", return_value=mock_merger),
        ):
            result = runner.invoke(
                profile_command,
                ["merge", "p1", "p2", "-o", "merged", "--show-conflicts"],
                input="n\n",
            )
        assert result.exit_code == 0
        assert "Cancelled" in result.output

    def test_merge_no_conflicts(self, runner, mock_manager, mock_profile):
        mock_merger = MagicMock()
        mock_merger.get_merge_conflicts.return_value = {}
        mock_merger.merge_profiles.return_value = mock_profile
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMerger", return_value=mock_merger),
        ):
            result = runner.invoke(
                profile_command,
                ["merge", "p1", "p2", "-o", "merged", "--show-conflicts"],
            )
        assert result.exit_code == 0
        assert "No conflicts detected" in result.output

    def test_merge_failure(self, runner, mock_manager):
        mock_merger = MagicMock()
        mock_merger.merge_profiles.return_value = None
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMerger", return_value=mock_merger),
        ):
            result = runner.invoke(
                profile_command, ["merge", "p1", "p2", "-o", "merged"]
            )
        assert result.exit_code != 0
        assert "Failed to merge" in result.output

    def test_merge_with_strategy(self, runner, mock_manager, mock_profile):
        mock_merger = MagicMock()
        mock_merger.merge_profiles.return_value = mock_profile
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMerger", return_value=mock_merger),
        ):
            result = runner.invoke(
                profile_command, ["merge", "p1", "p2", "-o", "merged", "-s", "recent"]
            )
        assert result.exit_code == 0
        mock_merger.merge_profiles.assert_called_once_with(["p1", "p2"], "recent", "merged")


# ============================================================================
# Template Tests
# ============================================================================


@pytest.mark.unit
class TestTemplateCommands:
    """Tests for the 'template' subcommand group."""

    def test_list_templates(self, runner, mock_manager):
        mock_tmpl = MagicMock()
        mock_tmpl.list_templates.return_value = ["developer", "photographer"]
        mock_tmpl.get_template.side_effect = [
            {"description": "Dev template"},
            {"description": "Photo template"},
        ]
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.TemplateManager", return_value=mock_tmpl),
        ):
            result = runner.invoke(profile_command, ["template", "list"])
        assert result.exit_code == 0
        assert "developer" in result.output
        assert "photographer" in result.output

    def test_preview_template_success(self, runner, mock_manager):
        mock_tmpl = MagicMock()
        mock_tmpl.preview_template.return_value = {
            "name": "developer",
            "description": "A developer template",
            "preferences_summary": {
                "naming_patterns": ["snake_case"],
                "folder_mappings": ["src -> Source"],
                "category_overrides": 2,
            },
            "learned_patterns": ["code_pattern"],
            "confidence_levels": {"categorize": 0.85},
        }
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.TemplateManager", return_value=mock_tmpl),
        ):
            result = runner.invoke(profile_command, ["template", "preview", "developer"])
        assert result.exit_code == 0
        assert "Template Preview: developer" in result.output
        assert "snake_case" in result.output

    def test_preview_template_not_found(self, runner, mock_manager):
        mock_tmpl = MagicMock()
        mock_tmpl.preview_template.return_value = None
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.TemplateManager", return_value=mock_tmpl),
        ):
            result = runner.invoke(profile_command, ["template", "preview", "missing"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_apply_template_success(self, runner, mock_manager, mock_profile):
        mock_tmpl = MagicMock()
        mock_tmpl.create_profile_from_template.return_value = mock_profile
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.TemplateManager", return_value=mock_tmpl),
        ):
            result = runner.invoke(
                profile_command, ["template", "apply", "developer", "my-dev"]
            )
        assert result.exit_code == 0
        assert "Created profile 'my-dev' from template 'developer'" in result.output

    def test_apply_template_with_activate(self, runner, mock_manager, mock_profile):
        mock_tmpl = MagicMock()
        mock_tmpl.create_profile_from_template.return_value = mock_profile
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.TemplateManager", return_value=mock_tmpl),
        ):
            result = runner.invoke(
                profile_command, ["template", "apply", "developer", "my-dev", "-a"]
            )
        assert result.exit_code == 0
        assert "Activated profile: my-dev" in result.output

    def test_apply_template_failure(self, runner, mock_manager):
        mock_tmpl = MagicMock()
        mock_tmpl.create_profile_from_template.return_value = None
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.TemplateManager", return_value=mock_tmpl),
        ):
            result = runner.invoke(
                profile_command, ["template", "apply", "bad", "my-prof"]
            )
        assert result.exit_code != 0
        assert "Failed to create" in result.output


# ============================================================================
# Migration Tests
# ============================================================================


@pytest.mark.unit
class TestMigrateProfile:
    """Tests for the 'migrate' subcommand."""

    def test_migrate_success(self, runner, mock_manager):
        mock_migrator = MagicMock()
        mock_migrator.migrate_version.return_value = True
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMigrator", return_value=mock_migrator),
        ):
            result = runner.invoke(
                profile_command, ["migrate", "old", "--to-version", "2.0"]
            )
        assert result.exit_code == 0
        assert "Migrated profile" in result.output
        mock_migrator.migrate_version.assert_called_once_with("old", "2.0", backup=True)

    def test_migrate_no_backup(self, runner, mock_manager):
        mock_migrator = MagicMock()
        mock_migrator.migrate_version.return_value = True
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMigrator", return_value=mock_migrator),
        ):
            result = runner.invoke(
                profile_command, ["migrate", "old", "--to-version", "2.0", "--no-backup"]
            )
        assert result.exit_code == 0
        mock_migrator.migrate_version.assert_called_once_with("old", "2.0", backup=False)

    def test_migrate_failure(self, runner, mock_manager):
        mock_migrator = MagicMock()
        mock_migrator.migrate_version.return_value = False
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMigrator", return_value=mock_migrator),
        ):
            result = runner.invoke(
                profile_command, ["migrate", "bad", "--to-version", "2.0"]
            )
        assert result.exit_code != 0
        assert "Failed to migrate" in result.output


@pytest.mark.unit
class TestValidateProfile:
    """Tests for the 'validate' subcommand."""

    def test_validate_success(self, runner, mock_manager):
        mock_migrator = MagicMock()
        mock_migrator.validate_migration.return_value = True
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMigrator", return_value=mock_migrator),
        ):
            result = runner.invoke(profile_command, ["validate", "my-profile"])
        assert result.exit_code == 0
        assert "is valid" in result.output

    def test_validate_failure(self, runner, mock_manager):
        mock_migrator = MagicMock()
        mock_migrator.validate_migration.return_value = False
        with (
            patch("file_organizer.cli.profile.get_profile_manager", return_value=mock_manager),
            patch("file_organizer.cli.profile.ProfileMigrator", return_value=mock_migrator),
        ):
            result = runner.invoke(profile_command, ["validate", "bad-profile"])
        assert result.exit_code != 0
        assert "validation failed" in result.output
