"""Integration tests for template_manager module branch coverage.

Targets uncovered branches in:
  - create_profile_from_template: template not found, profile already exists,
      profile is None after create_profile, success=False cleanup, exception handler
  - _apply_customizations: folder_mappings, category_overrides, description branches
  - create_custom_template: profile not found, template already exists, exception handler
  - compare_templates: < 2 valid templates, template None warning, exception handler
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(tmp_path: Path):
    from file_organizer.services.intelligence.profile_manager import ProfileManager
    from file_organizer.services.intelligence.template_manager import TemplateManager

    pm = ProfileManager(tmp_path / "profiles")
    tm = TemplateManager(pm)
    return pm, tm


# ---------------------------------------------------------------------------
# create_profile_from_template — various branches
# ---------------------------------------------------------------------------


class TestCreateProfileFromTemplateBranches:
    def test_unknown_template_returns_none(self, tmp_path: Path) -> None:
        """template not found → returns None (line 325-327)."""
        _, tm = _make_manager(tmp_path)
        result = tm.create_profile_from_template("nonexistent_tpl", "MyProfile")
        assert result is None

    def test_profile_already_exists_returns_none(self, tmp_path: Path) -> None:
        """profile already exists → returns None (lines 330-332)."""
        pm, tm = _make_manager(tmp_path)
        pm.create_profile("ExistingProfile", "already here")

        result = tm.create_profile_from_template("work", "ExistingProfile")
        assert result is None

    def test_profile_is_none_after_create_returns_none(self, tmp_path: Path) -> None:
        """profile_manager.create_profile returns None → method returns None (line 341-342)."""
        pm, tm = _make_manager(tmp_path)

        with patch.object(pm, "create_profile", return_value=None):
            result = tm.create_profile_from_template("work", "AnyProfile")
        assert result is None

    def test_update_failure_cleans_up_and_returns_none(self, tmp_path: Path) -> None:
        """update_profile returns False → delete_profile called, returns None (lines 352-355)."""
        pm, tm = _make_manager(tmp_path)

        with patch.object(pm, "update_profile", return_value=False):
            result = tm.create_profile_from_template("personal", "CleanupTest")
        assert result is None
        # The partially-created profile should have been deleted
        assert not pm.profile_exists("CleanupTest")

    def test_exception_in_create_returns_none(self, tmp_path: Path) -> None:
        """Exception during template application → returns None (lines 359-361)."""
        pm, tm = _make_manager(tmp_path)

        with patch.object(pm, "create_profile", side_effect=RuntimeError("boom")):
            result = tm.create_profile_from_template("photography", "Boom")
        assert result is None

    def test_successful_creation_from_template(self, tmp_path: Path) -> None:
        """Happy-path: creates profile from template with correct data."""
        _, tm = _make_manager(tmp_path)
        profile = tm.create_profile_from_template("work", "WorkProfile")
        assert profile is not None
        assert profile.profile_name == "WorkProfile"

    def test_create_with_customizations_applied(self, tmp_path: Path) -> None:
        """customize param triggers _apply_customizations (line 336)."""
        _, tm = _make_manager(tmp_path)
        customize: dict[str, Any] = {
            "naming_patterns": {"separator": "__"},
            "folder_mappings": {"custom_dir": "Custom/Dir"},
            "category_overrides": {"my_ext": "custom_category"},
            "description": "My custom work profile",
        }
        profile = tm.create_profile_from_template("work", "CustomWork", customize=customize)
        assert profile is not None
        # Verify the customization payload was actually applied, not ignored
        prefs = profile.preferences.get("global", {})
        assert prefs.get("folder_mappings", {}).get("custom_dir") == "Custom/Dir"
        assert prefs.get("category_overrides", {}).get("my_ext") == "custom_category"


# ---------------------------------------------------------------------------
# _apply_customizations — individual branches
# ---------------------------------------------------------------------------


class TestApplyCustomizationsBranches:
    def test_folder_mappings_branch(self, tmp_path: Path) -> None:
        """folder_mappings key in customize updates folder mappings (lines 385-386)."""
        _, tm = _make_manager(tmp_path)
        template = tm.get_template("work")
        assert template is not None

        result = tm._apply_customizations(template, {"folder_mappings": {"special": "Special/Dir"}})
        assert result["preferences"]["global"]["folder_mappings"]["special"] == "Special/Dir"
        # Original mappings preserved
        assert "documents" in result["preferences"]["global"]["folder_mappings"]

    def test_category_overrides_branch(self, tmp_path: Path) -> None:
        """category_overrides key in customize updates overrides (lines 391-392)."""
        _, tm = _make_manager(tmp_path)
        template = tm.get_template("work")
        assert template is not None

        result = tm._apply_customizations(template, {"category_overrides": {"memo": "internal"}})
        assert result["preferences"]["global"]["category_overrides"]["memo"] == "internal"

    def test_description_branch(self, tmp_path: Path) -> None:
        """description key in customize replaces description (lines 397-398)."""
        _, tm = _make_manager(tmp_path)
        template = tm.get_template("personal")
        assert template is not None

        result = tm._apply_customizations(template, {"description": "My description"})
        assert result["description"] == "My description"

    def test_naming_patterns_branch(self, tmp_path: Path) -> None:
        """naming_patterns key in customize updates naming patterns (lines 379-381)."""
        _, tm = _make_manager(tmp_path)
        template = tm.get_template("work")
        assert template is not None

        result = tm._apply_customizations(template, {"naming_patterns": {"separator": "-"}})
        assert result["preferences"]["global"]["naming_patterns"]["separator"] == "-"

    def test_no_customizations_returns_unchanged(self, tmp_path: Path) -> None:
        """Empty customize dict returns template unchanged."""
        _, tm = _make_manager(tmp_path)
        template = tm.get_template("work")
        assert template is not None

        result = tm._apply_customizations(template, {})
        assert result["description"] == template["description"]


# ---------------------------------------------------------------------------
# create_custom_template — various branches
# ---------------------------------------------------------------------------


class TestCreateCustomTemplateBranches:
    def test_profile_not_found_returns_false(self, tmp_path: Path) -> None:
        """Profile not found → returns False, prints error (lines 415-417)."""
        _, tm = _make_manager(tmp_path)
        result = tm.create_custom_template("nonexistent_profile", "new_tpl")
        assert result is False

    def test_template_name_already_exists_returns_false(self, tmp_path: Path) -> None:
        """Template already exists → returns False (lines 420-422)."""
        pm, tm = _make_manager(tmp_path)
        pm.create_profile("MyProfile", "A profile")

        # Try to create a template with an existing built-in name
        result = tm.create_custom_template("MyProfile", "work")  # 'work' already exists
        assert result is False

    def test_create_custom_template_success(self, tmp_path: Path) -> None:
        """Creates custom template from profile successfully."""
        pm, tm = _make_manager(tmp_path)
        pm.create_profile("SourceProfile", "Source for template")

        result = tm.create_custom_template("SourceProfile", "my_custom_tpl")
        assert result is True
        assert "my_custom_tpl" in tm.list_templates()

    def test_exception_in_create_custom_template_returns_false(self, tmp_path: Path) -> None:
        """Exception in body → returns False (lines 442-444)."""
        pm, tm = _make_manager(tmp_path)
        pm.create_profile("ErrProfile", "will error")

        with patch.object(pm, "get_profile", side_effect=RuntimeError("explode")):
            result = tm.create_custom_template("ErrProfile", "boom_tpl")
        assert result is False


# ---------------------------------------------------------------------------
# compare_templates — various branches
# ---------------------------------------------------------------------------


class TestCompareTemplatesBranches:
    def test_fewer_than_two_valid_templates_returns_none(self, tmp_path: Path) -> None:
        """Less than 2 valid templates → prints error, returns None (lines 531-533)."""
        _, tm = _make_manager(tmp_path)
        result = tm.compare_templates(["work"])
        assert result is None

    def test_unknown_template_skipped_with_warning(self, tmp_path: Path) -> None:
        """Unknown template name → skipped with warning; remaining checked (lines 527-529)."""
        _, tm = _make_manager(tmp_path)
        # One valid template, one invalid → only 1 valid → returns None
        result = tm.compare_templates(["work", "nonexistent_template"])
        assert result is None

    def test_two_unknown_templates_returns_none(self, tmp_path: Path) -> None:
        """Both templates unknown → 0 valid → returns None."""
        _, tm = _make_manager(tmp_path)
        result = tm.compare_templates(["invalid_a", "invalid_b"])
        assert result is None

    def test_compare_two_valid_templates_returns_comparison(self, tmp_path: Path) -> None:
        """Two valid templates → returns comparison dict."""
        _, tm = _make_manager(tmp_path)
        result = tm.compare_templates(["work", "personal"])
        assert result is not None
        assert "templates" in result
        assert len(result["templates"]) == 2

    def test_compare_three_templates(self, tmp_path: Path) -> None:
        """Three valid templates produces full comparison."""
        _, tm = _make_manager(tmp_path)
        result = tm.compare_templates(["work", "personal", "photography"])
        assert result is not None
        assert len(result["templates"]) == 3

    def test_exception_in_compare_returns_none(self, tmp_path: Path) -> None:
        """Exception in body → returns None (lines 554-556)."""
        _, tm = _make_manager(tmp_path)

        with patch.object(tm, "get_template", side_effect=RuntimeError("compare_boom")):
            result = tm.compare_templates(["work", "personal"])
        assert result is None


# ---------------------------------------------------------------------------
# Additional coverage: list_templates, get_template, preview_template
# ---------------------------------------------------------------------------


class TestTemplateManagerMisc:
    def test_list_templates_returns_all_defaults(self, tmp_path: Path) -> None:
        """list_templates returns all 5 default template names."""
        _, tm = _make_manager(tmp_path)
        names = tm.list_templates()
        assert "work" in names
        assert "personal" in names
        assert "photography" in names
        assert "development" in names
        assert "academic" in names

    def test_get_template_case_insensitive(self, tmp_path: Path) -> None:
        """get_template is case-insensitive."""
        _, tm = _make_manager(tmp_path)
        assert tm.get_template("WORK") is not None
        assert tm.get_template("Work") is not None

    def test_get_template_not_found_returns_none(self, tmp_path: Path) -> None:
        """get_template returns None for unknown templates."""
        _, tm = _make_manager(tmp_path)
        assert tm.get_template("does_not_exist") is None

    def test_preview_template_not_found_returns_none(self, tmp_path: Path) -> None:
        """preview_template prints error and returns None when template not found."""
        _, tm = _make_manager(tmp_path)
        assert tm.preview_template("ghost") is None

    def test_preview_template_returns_summary(self, tmp_path: Path) -> None:
        """preview_template returns structured preview dict."""
        _, tm = _make_manager(tmp_path)
        preview = tm.preview_template("work")
        assert preview is not None
        assert preview["template_name"] == "work"
        assert "description" in preview

    def test_get_template_recommendations_by_file_types(self, tmp_path: Path) -> None:
        """Recommendations based on file types."""
        _, tm = _make_manager(tmp_path)
        recs = tm.get_template_recommendations(file_types=[".py", ".js"])
        assert "development" in recs

    def test_get_template_recommendations_by_use_case(self, tmp_path: Path) -> None:
        """Recommendations based on use case keyword."""
        _, tm = _make_manager(tmp_path)
        recs = tm.get_template_recommendations(use_case="work business")
        assert "work" in recs

    def test_get_template_recommendations_dedup(self, tmp_path: Path) -> None:
        """No duplicate recommendations."""
        _, tm = _make_manager(tmp_path)
        recs = tm.get_template_recommendations(file_types=[".pdf"], use_case="work documents")
        assert len(recs) == len(set(recs))
