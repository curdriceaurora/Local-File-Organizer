"""Integration tests for profile management CLI commands.

Covers: list, create, activate, delete, show (current), export, import,
merge, template (list/preview/apply), migrate, validate.

All external managers are mocked — zero real file I/O.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from file_organizer.cli.profile import profile_command

pytestmark = [pytest.mark.integration, pytest.mark.ci]

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(
    name: str = "myprofile",
    description: str = "A test profile",
    preferences: dict | None = None,
    is_active: bool = False,
) -> MagicMock:
    """Build a minimal profile mock with the attributes the CLI reads."""
    p = MagicMock()
    p.profile_name = name
    p.description = description
    p.created = "2024-01-01"
    p.updated = "2024-01-02"
    p.profile_version = "1.0"
    p.preferences = preferences or {}
    p.learned_patterns = {}
    p.confidence_data = {}
    return p


# ---------------------------------------------------------------------------
# list command
# ---------------------------------------------------------------------------


class TestListProfiles:
    def test_list_empty(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.list_profiles.return_value = []
            result = runner.invoke(profile_command, ["list"])
        assert result.exit_code == 0
        assert "No profiles found" in result.output

    def test_list_single_active_profile(self) -> None:
        profile = _make_profile("work")
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            inst = mock_cls.return_value
            inst.list_profiles.return_value = [profile]
            inst._get_active_profile_name.return_value = "work"
            result = runner.invoke(profile_command, ["list"])
        assert result.exit_code == 0
        assert "work" in result.output
        assert "[ACTIVE]" in result.output

    def test_list_multiple_profiles_inactive(self) -> None:
        p1 = _make_profile("alpha")
        p2 = _make_profile("beta")
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            inst = mock_cls.return_value
            inst.list_profiles.return_value = [p1, p2]
            inst._get_active_profile_name.return_value = "other"
            result = runner.invoke(profile_command, ["list"])
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "beta" in result.output
        assert "[ACTIVE]" not in result.output

    def test_list_shows_preference_counts(self) -> None:
        profile = _make_profile(
            "prefs-profile",
            preferences={"global": {"a": 1, "b": 2}, "directory_specific": {"x": 1}},
        )
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            inst = mock_cls.return_value
            inst.list_profiles.return_value = [profile]
            inst._get_active_profile_name.return_value = ""
            result = runner.invoke(profile_command, ["list"])
        assert result.exit_code == 0
        assert "2 global" in result.output
        assert "1 directory-specific" in result.output


# ---------------------------------------------------------------------------
# create command
# ---------------------------------------------------------------------------


class TestCreateProfile:
    def test_create_success(self) -> None:
        profile = _make_profile("newprofile")
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.create_profile.return_value = profile
            result = runner.invoke(profile_command, ["create", "newprofile"])
        assert result.exit_code == 0
        assert "Created profile" in result.output
        assert "newprofile" in result.output

    def test_create_with_description(self) -> None:
        profile = _make_profile("desc-profile")
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            inst = mock_cls.return_value
            inst.create_profile.return_value = profile
            result = runner.invoke(
                profile_command, ["create", "desc-profile", "--description", "My desc"]
            )
        assert result.exit_code == 0
        inst.create_profile.assert_called_once_with("desc-profile", "My desc")

    def test_create_and_activate(self) -> None:
        profile = _make_profile("activated")
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            inst = mock_cls.return_value
            inst.create_profile.return_value = profile
            inst.activate_profile.return_value = True
            result = runner.invoke(profile_command, ["create", "activated", "--activate"])
        assert result.exit_code == 0
        assert "Created profile" in result.output
        assert "Activated profile" in result.output

    def test_create_returns_none_aborts(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.create_profile.return_value = None
            result = runner.invoke(profile_command, ["create", "bad"])
        # Abort causes non-zero or output about failure
        assert "Failed to create profile" in result.output

    def test_create_activate_fails(self) -> None:
        profile = _make_profile("fail-act")
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            inst = mock_cls.return_value
            inst.create_profile.return_value = profile
            inst.activate_profile.return_value = False
            result = runner.invoke(profile_command, ["create", "fail-act", "-a"])
        assert result.exit_code == 0
        assert "Failed to activate" in result.output


# ---------------------------------------------------------------------------
# activate command
# ---------------------------------------------------------------------------


class TestActivateProfile:
    def test_activate_success(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.activate_profile.return_value = True
            result = runner.invoke(profile_command, ["activate", "work"])
        assert result.exit_code == 0
        assert "Activated profile" in result.output
        assert "work" in result.output

    def test_activate_not_found(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.activate_profile.return_value = False
            result = runner.invoke(profile_command, ["activate", "ghost"])
        assert result.exit_code != 0
        assert "Failed to activate profile" in result.output


# ---------------------------------------------------------------------------
# delete command
# ---------------------------------------------------------------------------


class TestDeleteProfile:
    def test_delete_with_force_flag(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.delete_profile.return_value = True
            result = runner.invoke(profile_command, ["delete", "old", "--force"])
        assert result.exit_code == 0
        assert "Deleted profile" in result.output
        assert "old" in result.output

    def test_delete_confirm_yes(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.delete_profile.return_value = True
            result = runner.invoke(profile_command, ["delete", "old"], input="y\n")
        assert result.exit_code == 0
        assert "Deleted profile" in result.output

    def test_delete_confirm_no_cancels(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.delete_profile.return_value = True
            result = runner.invoke(profile_command, ["delete", "old"], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled" in result.output

    def test_delete_fails_aborts(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.delete_profile.return_value = False
            result = runner.invoke(profile_command, ["delete", "noexist", "--force"])
        assert result.exit_code != 0
        assert "Failed to delete profile" in result.output


# ---------------------------------------------------------------------------
# current command
# ---------------------------------------------------------------------------


class TestShowCurrentProfile:
    def test_show_current_success(self) -> None:
        profile = _make_profile("mywork")
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.get_active_profile.return_value = profile
            result = runner.invoke(profile_command, ["current"])
        assert result.exit_code == 0
        assert "Active Profile" in result.output
        assert "mywork" in result.output

    def test_show_current_no_active_profile(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.get_active_profile.return_value = None
            result = runner.invoke(profile_command, ["current"])
        assert result.exit_code != 0
        assert "No active profile found" in result.output

    def test_show_current_statistics(self) -> None:
        profile = _make_profile(
            "stats-profile",
            preferences={"global": {"k": "v"}, "directory_specific": {}},
        )
        profile.learned_patterns = {"p1": 1, "p2": 2}
        profile.confidence_data = {"c1": 0.9}
        with patch("file_organizer.cli.profile.ProfileManager") as mock_cls:
            mock_cls.return_value.get_active_profile.return_value = profile
            result = runner.invoke(profile_command, ["current"])
        assert result.exit_code == 0
        assert "Global preferences: 1" in result.output
        assert "Learned patterns: 2" in result.output
        assert "Confidence data: 1" in result.output


# ---------------------------------------------------------------------------
# export command
# ---------------------------------------------------------------------------


class TestExportProfile:
    def test_export_full_success(self, tmp_path) -> None:
        output_file = str(tmp_path / "out.json")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileExporter") as mock_exp:
                mock_exp.return_value.export_profile.return_value = True
                result = runner.invoke(
                    profile_command, ["export", "myprofile", "--output", output_file]
                )
        assert result.exit_code == 0
        assert "Exported profile" in result.output
        assert "myprofile" in result.output

    def test_export_selective_success(self, tmp_path) -> None:
        output_file = str(tmp_path / "out.json")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileExporter") as mock_exp:
                mock_exp.return_value.export_selective.return_value = True
                result = runner.invoke(
                    profile_command,
                    [
                        "export",
                        "myprofile",
                        "--output",
                        output_file,
                        "--selective",
                        "global",
                    ],
                )
        assert result.exit_code == 0
        assert "Exported profile" in result.output

    def test_export_failure_aborts(self, tmp_path) -> None:
        output_file = str(tmp_path / "out.json")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileExporter") as mock_exp:
                mock_exp.return_value.export_profile.return_value = False
                result = runner.invoke(
                    profile_command, ["export", "myprofile", "--output", output_file]
                )
        assert result.exit_code != 0
        assert "Failed to export profile" in result.output


# ---------------------------------------------------------------------------
# import command
# ---------------------------------------------------------------------------


class TestImportProfile:
    def test_import_success(self, tmp_path) -> None:
        import_file = tmp_path / "profile.json"
        import_file.write_text("{}")  # must exist for click.Path(exists=True)
        profile = _make_profile("imported")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileImporter") as mock_imp:
                mock_imp.return_value.import_profile.return_value = profile
                result = runner.invoke(profile_command, ["import", str(import_file)])
        assert result.exit_code == 0
        assert "Imported profile" in result.output
        assert "imported" in result.output

    def test_import_returns_none_aborts(self, tmp_path) -> None:
        import_file = tmp_path / "profile.json"
        import_file.write_text("{}")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileImporter") as mock_imp:
                mock_imp.return_value.import_profile.return_value = None
                result = runner.invoke(profile_command, ["import", str(import_file)])
        assert result.exit_code != 0
        assert "Failed to import profile" in result.output

    def test_import_with_new_name(self, tmp_path) -> None:
        import_file = tmp_path / "profile.json"
        import_file.write_text("{}")
        profile = _make_profile("renamed")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileImporter") as mock_imp:
                mock_imp.return_value.import_profile.return_value = profile
                result = runner.invoke(
                    profile_command,
                    ["import", str(import_file), "--as", "renamed"],
                )
        assert result.exit_code == 0
        mock_imp.return_value.import_profile.assert_called_once()
        call_args = mock_imp.return_value.import_profile.call_args
        assert call_args[0][1] == "renamed"

    def test_import_preview_success(self, tmp_path) -> None:
        import_file = tmp_path / "profile.json"
        import_file.write_text("{}")
        preview_data = {
            "profile_name": "prev-profile",
            "description": "Preview desc",
            "profile_version": "1.0",
            "export_type": "full",
            "preferences_count": {"global": 2},
            "learned_patterns_count": 3,
            "confidence_data_count": 1,
            "validation": {"valid": True, "errors": [], "warnings": []},
        }
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileImporter") as mock_imp:
                mock_imp.return_value.preview_import.return_value = preview_data
                result = runner.invoke(profile_command, ["import", str(import_file), "--preview"])
        assert result.exit_code == 0
        assert "Import Preview" in result.output
        assert "prev-profile" in result.output
        assert "Valid: True" in result.output

    def test_import_preview_none_aborts(self, tmp_path) -> None:
        import_file = tmp_path / "profile.json"
        import_file.write_text("{}")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileImporter") as mock_imp:
                mock_imp.return_value.preview_import.return_value = None
                result = runner.invoke(profile_command, ["import", str(import_file), "--preview"])
        assert result.exit_code != 0
        assert "Failed to preview import" in result.output


# ---------------------------------------------------------------------------
# merge command
# ---------------------------------------------------------------------------


class TestMergeProfiles:
    def test_merge_success(self) -> None:
        merged = _make_profile("merged-result")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileMerger") as mock_merger:
                mock_merger.return_value.merge_profiles.return_value = merged
                result = runner.invoke(
                    profile_command,
                    ["merge", "alpha", "beta", "--output", "merged-result"],
                )
        assert result.exit_code == 0
        assert "Merged 2 profiles into" in result.output
        assert "merged-result" in result.output

    def test_merge_too_few_profiles_errors(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileMerger"):
                result = runner.invoke(
                    profile_command,
                    ["merge", "alpha", "--output", "merged-result"],
                )
        assert result.exit_code != 0
        assert "Need at least 2 profiles" in result.output

    def test_merge_returns_none_aborts(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileMerger") as mock_merger:
                mock_merger.return_value.merge_profiles.return_value = None
                result = runner.invoke(
                    profile_command,
                    ["merge", "alpha", "beta", "--output", "merged-result"],
                )
        assert result.exit_code != 0
        assert "Failed to merge profiles" in result.output

    def test_merge_with_strategy(self) -> None:
        merged = _make_profile("merged-recent")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileMerger") as mock_merger:
                mock_merger.return_value.merge_profiles.return_value = merged
                result = runner.invoke(
                    profile_command,
                    [
                        "merge",
                        "alpha",
                        "beta",
                        "--output",
                        "merged-recent",
                        "--strategy",
                        "recent",
                    ],
                )
        assert result.exit_code == 0
        assert "recent" in result.output

    def test_merge_show_conflicts_no_conflicts(self) -> None:
        merged = _make_profile("merged-no-conf")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileMerger") as mock_merger:
                mock_merger.return_value.get_merge_conflicts.return_value = {}
                mock_merger.return_value.merge_profiles.return_value = merged
                result = runner.invoke(
                    profile_command,
                    [
                        "merge",
                        "alpha",
                        "beta",
                        "--output",
                        "merged-no-conf",
                        "--show-conflicts",
                    ],
                )
        assert result.exit_code == 0
        assert "No conflicts detected" in result.output

    def test_merge_show_conflicts_confirms_yes(self) -> None:
        merged = _make_profile("merged-conf")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileMerger") as mock_merger:
                mock_merger.return_value.get_merge_conflicts.return_value = {
                    "naming": ["snake_case", "camelCase"]
                }
                mock_merger.return_value.merge_profiles.return_value = merged
                result = runner.invoke(
                    profile_command,
                    [
                        "merge",
                        "alpha",
                        "beta",
                        "--output",
                        "merged-conf",
                        "--show-conflicts",
                    ],
                    input="y\n",
                )
        assert result.exit_code == 0
        assert "Conflicts detected" in result.output
        assert "Merged" in result.output


# ---------------------------------------------------------------------------
# template subcommands
# ---------------------------------------------------------------------------


class TestTemplateCommands:
    def test_list_templates(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.TemplateManager") as mock_tm:
                mock_tm.return_value.list_templates.return_value = ["starter", "developer"]
                mock_tm.return_value.get_template.side_effect = lambda name: {
                    "description": f"Template {name}"
                }
                result = runner.invoke(profile_command, ["template", "list"])
        assert result.exit_code == 0
        assert "starter" in result.output
        assert "developer" in result.output

    def test_list_templates_empty(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.TemplateManager") as mock_tm:
                mock_tm.return_value.list_templates.return_value = []
                result = runner.invoke(profile_command, ["template", "list"])
        assert result.exit_code == 0
        assert "Available Templates (0)" in result.output

    def test_apply_template_success(self) -> None:
        profile = _make_profile("from-template")
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.TemplateManager") as mock_tm:
                mock_tm.return_value.create_profile_from_template.return_value = profile
                result = runner.invoke(
                    profile_command, ["template", "apply", "starter", "from-template"]
                )
        assert result.exit_code == 0
        assert "Created profile 'from-template' from template 'starter'" in result.output

    def test_apply_template_and_activate(self) -> None:
        profile = _make_profile("from-template")
        with patch("file_organizer.cli.profile.ProfileManager") as mock_pm:
            with patch("file_organizer.cli.profile.TemplateManager") as mock_tm:
                mock_tm.return_value.create_profile_from_template.return_value = profile
                mock_pm.return_value.activate_profile.return_value = True
                result = runner.invoke(
                    profile_command,
                    ["template", "apply", "starter", "from-template", "--activate"],
                )
        assert result.exit_code == 0
        assert "Activated profile" in result.output

    def test_apply_template_returns_none_aborts(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.TemplateManager") as mock_tm:
                mock_tm.return_value.create_profile_from_template.return_value = None
                result = runner.invoke(
                    profile_command, ["template", "apply", "bad-template", "newprofile"]
                )
        assert result.exit_code != 0
        assert "Failed to create profile from template" in result.output

    def test_preview_template_success(self) -> None:
        preview = {
            "name": "starter",
            "description": "Starter template",
            "preferences_summary": {
                "naming_patterns": ["snake_case"],
                "folder_mappings": ["documents"],
                "category_overrides": 2,
            },
            "learned_patterns": ["docs", "code"],
            "confidence_levels": {"high": 0.9},
        }
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.TemplateManager") as mock_tm:
                mock_tm.return_value.preview_template.return_value = preview
                result = runner.invoke(profile_command, ["template", "preview", "starter"])
        assert result.exit_code == 0
        assert "Template Preview: starter" in result.output
        assert "Starter template" in result.output

    def test_preview_template_not_found(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.TemplateManager") as mock_tm:
                mock_tm.return_value.preview_template.return_value = None
                result = runner.invoke(profile_command, ["template", "preview", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# migrate command
# ---------------------------------------------------------------------------


class TestMigrateProfile:
    def test_migrate_success(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileMigrator") as mock_mig:
                mock_mig.return_value.migrate_version.return_value = True
                result = runner.invoke(
                    profile_command,
                    ["migrate", "myprofile", "--to-version", "2.0"],
                )
        assert result.exit_code == 0
        assert "Migrated profile 'myprofile' to version 2.0" in result.output

    def test_migrate_with_no_backup(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileMigrator") as mock_mig:
                mock_mig.return_value.migrate_version.return_value = True
                result = runner.invoke(
                    profile_command,
                    ["migrate", "myprofile", "--to-version", "2.0", "--no-backup"],
                )
        assert result.exit_code == 0
        mock_mig.return_value.migrate_version.assert_called_once_with(
            "myprofile", "2.0", backup=False
        )

    def test_migrate_failure_aborts(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileMigrator") as mock_mig:
                mock_mig.return_value.migrate_version.return_value = False
                result = runner.invoke(
                    profile_command,
                    ["migrate", "myprofile", "--to-version", "3.0"],
                )
        assert result.exit_code != 0
        assert "Failed to migrate profile" in result.output


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------


class TestValidateProfile:
    def test_validate_success(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileMigrator") as mock_mig:
                mock_mig.return_value.validate_migration.return_value = True
                result = runner.invoke(profile_command, ["validate", "myprofile"])
        assert result.exit_code == 0
        assert "is valid" in result.output

    def test_validate_failure_aborts(self) -> None:
        with patch("file_organizer.cli.profile.ProfileManager"):
            with patch("file_organizer.cli.profile.ProfileMigrator") as mock_mig:
                mock_mig.return_value.validate_migration.return_value = False
                result = runner.invoke(profile_command, ["validate", "broken-profile"])
        assert result.exit_code != 0
        assert "validation failed" in result.output
