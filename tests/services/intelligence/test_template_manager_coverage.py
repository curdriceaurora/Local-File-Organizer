"""Coverage tests for TemplateManager — targets uncovered branches."""

from __future__ import annotations

import pytest

from file_organizer.services.intelligence.profile_manager import ProfileManager
from file_organizer.services.intelligence.template_manager import TemplateManager

pytestmark = pytest.mark.unit


@pytest.fixture()
def tm(tmp_path):
    pm = ProfileManager(storage_path=tmp_path / "profiles")
    return TemplateManager(profile_manager=pm)


# ---------------------------------------------------------------------------
# list / get / preview
# ---------------------------------------------------------------------------


class TestListGetPreview:
    def test_list_templates(self, tm):
        names = tm.list_templates()
        assert "work" in names
        assert "personal" in names

    def test_get_existing_template(self, tm):
        t = tm.get_template("work")
        assert t is not None
        assert t["name"] == "Work Profile"

    def test_get_case_insensitive(self, tm):
        t = tm.get_template("WORK")
        assert t is not None

    def test_get_nonexistent(self, tm):
        assert tm.get_template("nonexistent") is None

    def test_preview_existing(self, tm):
        preview = tm.preview_template("photography")
        assert preview is not None
        assert "naming_patterns" in preview["preferences_summary"]

    def test_preview_nonexistent(self, tm):
        assert tm.preview_template("nonexistent") is None


# ---------------------------------------------------------------------------
# create_profile_from_template
# ---------------------------------------------------------------------------


class TestCreateProfileFromTemplate:
    def test_create_from_template(self, tm):
        profile = tm.create_profile_from_template("work", "my_work")
        assert profile is not None
        assert profile.profile_name == "my_work"

    def test_create_nonexistent_template(self, tm):
        assert tm.create_profile_from_template("nope", "p") is None

    def test_create_duplicate_profile_name(self, tm):
        tm.create_profile_from_template("work", "dup")
        result = tm.create_profile_from_template("work", "dup")
        assert result is None

    def test_create_with_customizations(self, tm):
        customize = {
            "naming_patterns": {"date_format": "DD-MM-YYYY"},
            "folder_mappings": {"custom": "Custom/Dir"},
            "category_overrides": {"memo": "notes"},
            "description": "Custom work profile",
        }
        profile = tm.create_profile_from_template("work", "custom_work", customize=customize)
        assert profile is not None

    def test_create_with_failed_update(self, tm, tmp_path):
        """If update_profile fails, the profile should be cleaned up."""
        from unittest.mock import patch

        with patch.object(tm.profile_manager, "update_profile", return_value=False):
            result = tm.create_profile_from_template("work", "fail_work")
        assert result is None
        # Profile should have been deleted during cleanup
        assert not tm.profile_manager.profile_exists("fail_work")


# ---------------------------------------------------------------------------
# create_custom_template
# ---------------------------------------------------------------------------


class TestCreateCustomTemplate:
    def test_create_from_profile(self, tm):
        # default profile exists
        result = tm.create_custom_template("default", "my_template")
        assert result is True
        assert "my_template" in tm.list_templates()

    def test_create_from_nonexistent_profile(self, tm):
        result = tm.create_custom_template("nope", "t")
        assert result is False

    def test_create_duplicate_template_name(self, tm):
        result = tm.create_custom_template("default", "work")
        assert result is False


# ---------------------------------------------------------------------------
# get_template_recommendations
# ---------------------------------------------------------------------------


class TestGetTemplateRecommendations:
    def test_dev_files(self, tm):
        recs = tm.get_template_recommendations(file_types=[".py", ".js"])
        assert "development" in recs

    def test_image_files(self, tm):
        recs = tm.get_template_recommendations(file_types=[".jpg", ".raw"])
        assert "photography" in recs

    def test_doc_files(self, tm):
        recs = tm.get_template_recommendations(file_types=[".pdf", ".docx"])
        assert "work" in recs
        assert "academic" in recs

    def test_use_case_work(self, tm):
        recs = tm.get_template_recommendations(use_case="business corporate")
        assert "work" in recs

    def test_use_case_personal(self, tm):
        recs = tm.get_template_recommendations(use_case="personal home")
        assert "personal" in recs

    def test_use_case_photo(self, tm):
        recs = tm.get_template_recommendations(use_case="photo shoot")
        assert "photography" in recs

    def test_use_case_code(self, tm):
        recs = tm.get_template_recommendations(use_case="software development")
        assert "development" in recs

    def test_use_case_academic(self, tm):
        recs = tm.get_template_recommendations(use_case="university research")
        assert "academic" in recs

    def test_dedup_recommendations(self, tm):
        recs = tm.get_template_recommendations(file_types=[".pdf"], use_case="work business")
        # Should not have duplicates
        assert len(recs) == len(set(recs))

    def test_no_input(self, tm):
        recs = tm.get_template_recommendations()
        assert recs == []


# ---------------------------------------------------------------------------
# compare_templates
# ---------------------------------------------------------------------------


class TestCompareTemplates:
    def test_compare_two(self, tm):
        result = tm.compare_templates(["work", "personal"])
        assert result is not None
        assert len(result["templates"]) == 2

    def test_compare_one_invalid(self, tm):
        result = tm.compare_templates(["work", "nonexistent"])
        assert result is None  # Less than 2 valid

    def test_compare_all_invalid(self, tm):
        result = tm.compare_templates(["nope1", "nope2"])
        assert result is None
