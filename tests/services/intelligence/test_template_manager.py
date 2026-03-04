"""
Unit tests for Template Manager service.

Tests template loading, preview, profile creation from templates, customization,
custom template creation, template recommendations, and template comparison.
"""

from __future__ import annotations

from tempfile import TemporaryDirectory

import pytest

from file_organizer.services.intelligence.profile_manager import ProfileManager
from file_organizer.services.intelligence.template_manager import TemplateManager


@pytest.mark.unit
class TestTemplateManagerInit:
    """Tests for TemplateManager initialization."""

    def test_init_with_profile_manager(self):
        """Test initializing template manager with profile manager."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            assert tm.profile_manager is pm
            assert tm._templates is not None
            assert len(tm._templates) > 0

    def test_templates_are_deep_copied(self):
        """Test that templates are deep copied to avoid modification."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            # Modify internal templates
            tm._templates["work"]["name"] = "Modified"

            # Check that TEMPLATES class attr is unchanged
            assert TemplateManager.TEMPLATES["work"]["name"] == "Work Profile"
            assert tm._templates["work"]["name"] == "Modified"


@pytest.mark.unit
class TestListTemplates:
    """Tests for listing available templates."""

    def test_list_templates(self):
        """Test listing all available template names."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            templates = tm.list_templates()

            assert isinstance(templates, list)
            assert len(templates) >= 5  # At least work, personal, photography, development, academic
            assert "work" in templates
            assert "personal" in templates
            assert "photography" in templates
            assert "development" in templates
            assert "academic" in templates

    def test_list_templates_is_list_of_strings(self):
        """Test that list_templates returns list of strings."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            templates = tm.list_templates()

            assert all(isinstance(t, str) for t in templates)


@pytest.mark.unit
class TestGetTemplate:
    """Tests for retrieving template data."""

    def test_get_template_existing(self):
        """Test getting an existing template."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            template = tm.get_template("work")

            assert template is not None
            assert template["name"] == "Work Profile"
            assert "preferences" in template
            assert "learned_patterns" in template
            assert "confidence_data" in template

    def test_get_template_case_insensitive(self):
        """Test that template retrieval is case-insensitive."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            template_lower = tm.get_template("work")
            template_upper = tm.get_template("WORK")
            template_mixed = tm.get_template("WoRk")

            assert template_lower == template_upper == template_mixed

    def test_get_template_nonexistent(self):
        """Test getting a non-existent template returns None."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            template = tm.get_template("nonexistent_template")

            assert template is None

    def test_get_template_returns_deep_copy(self):
        """Test that get_template returns a deep copy."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            template1 = tm.get_template("work")
            template1["name"] = "Modified"

            template2 = tm.get_template("work")

            assert template2["name"] == "Work Profile"
            assert template1["name"] == "Modified"


@pytest.mark.unit
class TestPreviewTemplate:
    """Tests for template preview functionality."""

    def test_preview_template_existing(self):
        """Test previewing an existing template."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            preview = tm.preview_template("work")

            assert preview is not None
            assert preview["template_name"] == "work"
            assert preview["name"] == "Work Profile"
            assert "description" in preview
            assert "preferences_summary" in preview
            assert "learned_patterns" in preview
            assert "confidence_levels" in preview

    def test_preview_template_preferences_summary(self):
        """Test that preview includes preferences summary."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            preview = tm.preview_template("photography")

            assert "preferences_summary" in preview
            assert "naming_patterns" in preview["preferences_summary"]
            assert "folder_mappings" in preview["preferences_summary"]
            assert "category_overrides" in preview["preferences_summary"]

    def test_preview_template_nonexistent(self):
        """Test previewing a non-existent template returns None."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            preview = tm.preview_template("nonexistent")

            assert preview is None

    def test_preview_all_default_templates(self):
        """Test that all default templates can be previewed."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            for template_name in ["work", "personal", "photography", "development", "academic"]:
                preview = tm.preview_template(template_name)
                assert preview is not None
                assert preview["template_name"] == template_name


@pytest.mark.unit
class TestCreateProfileFromTemplate:
    """Tests for creating profiles from templates."""

    def test_create_profile_from_template_basic(self):
        """Test creating a basic profile from template."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            profile = tm.create_profile_from_template("work", "test_work_profile")

            assert profile is not None
            assert profile.profile_name == "test_work_profile"
            assert profile.preferences is not None
            assert profile.learned_patterns is not None

    def test_create_profile_from_template_nonexistent_template(self):
        """Test creating profile from non-existent template returns None."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            profile = tm.create_profile_from_template("nonexistent", "test_profile")

            assert profile is None

    def test_create_profile_from_template_existing_profile_name(self):
        """Test creating profile with existing name returns None."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            # Create first profile
            profile1 = tm.create_profile_from_template("work", "duplicate_profile")
            assert profile1 is not None

            # Try to create another with same name
            profile2 = tm.create_profile_from_template("personal", "duplicate_profile")
            assert profile2 is None

    def test_create_profile_from_template_with_customization(self):
        """Test creating profile from template with customizations."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            customize = {
                "naming_patterns": {
                    "separator": "-",
                    "case_style": "lower",
                },
                "folder_mappings": {
                    "projects": "My Projects",
                },
            }

            profile = tm.create_profile_from_template(
                "development", "custom_dev", customize=customize
            )

            assert profile is not None
            assert (
                profile.preferences["global"]["naming_patterns"]["separator"] == "-"
            )
            assert profile.preferences["global"]["folder_mappings"]["projects"] == "My Projects"

    def test_create_profile_inherits_template_data(self):
        """Test that created profile inherits template learned patterns and confidence."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            template = tm.get_template("academic")
            profile = tm.create_profile_from_template("academic", "test_academic")

            assert profile is not None
            assert profile.learned_patterns == template["learned_patterns"]
            assert profile.confidence_data == template["confidence_data"]


@pytest.mark.unit
class TestApplyCustomizations:
    """Tests for template customization."""

    def test_apply_customizations_naming_patterns(self):
        """Test customizing naming patterns."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            template = tm.get_template("work")
            customize = {
                "naming_patterns": {
                    "separator": "-",
                    "case_style": "lower",
                }
            }

            customized = tm._apply_customizations(template, customize)

            assert customized["preferences"]["global"]["naming_patterns"]["separator"] == "-"
            assert customized["preferences"]["global"]["naming_patterns"]["case_style"] == "lower"
            # Original should be unchanged
            assert template["preferences"]["global"]["naming_patterns"]["separator"] == "_"

    def test_apply_customizations_folder_mappings(self):
        """Test customizing folder mappings."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            template = tm.get_template("work")
            customize = {
                "folder_mappings": {
                    "documents": "My Documents",
                    "reports": "My Reports",
                }
            }

            customized = tm._apply_customizations(template, customize)

            assert customized["preferences"]["global"]["folder_mappings"]["documents"] == "My Documents"
            assert customized["preferences"]["global"]["folder_mappings"]["reports"] == "My Reports"

    def test_apply_customizations_description(self):
        """Test customizing template description."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            template = tm.get_template("personal")
            customize = {"description": "My Custom Profile"}

            customized = tm._apply_customizations(template, customize)

            assert customized["description"] == "My Custom Profile"

    def test_apply_customizations_multiple(self):
        """Test applying multiple customizations at once."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            template = tm.get_template("development")
            customize = {
                "naming_patterns": {"case_style": "lower"},
                "folder_mappings": {"projects": "work_projects"},
                "description": "Custom Dev Profile",
            }

            customized = tm._apply_customizations(template, customize)

            assert customized["preferences"]["global"]["naming_patterns"]["case_style"] == "lower"
            assert customized["preferences"]["global"]["folder_mappings"]["projects"] == "work_projects"
            assert customized["description"] == "Custom Dev Profile"


@pytest.mark.unit
class TestCreateCustomTemplate:
    """Tests for creating custom templates from profiles."""

    def test_create_custom_template_from_profile(self):
        """Test creating a custom template from an existing profile."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            # Create a profile from template first
            pm.create_profile("test_profile", "A test profile")
            pm.update_profile(
                "test_profile",
                preferences={"global": {"naming_patterns": {"separator": "_"}}},
                learned_patterns={"test": "data"},
                confidence_data={"test": 0.8},
            )

            success = tm.create_custom_template("test_profile", "custom_template")

            assert success is True
            assert "custom_template" in tm.list_templates()

    def test_create_custom_template_nonexistent_profile(self):
        """Test creating custom template from non-existent profile returns False."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            success = tm.create_custom_template("nonexistent", "custom_template")

            assert success is False

    def test_create_custom_template_existing_template_name(self):
        """Test creating custom template with existing name returns False."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            pm.create_profile("test_profile", "A test profile")

            success = tm.create_custom_template("test_profile", "work")

            assert success is False

    def test_custom_template_is_in_memory_only(self):
        """Test that custom templates are in-memory only (not persisted)."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            pm.create_profile("test_profile", "A test profile")
            pm.update_profile(
                "test_profile",
                preferences={"global": {"naming_patterns": {}}},
                learned_patterns={},
                confidence_data={},
            )

            tm.create_custom_template("test_profile", "memory_template")

            # Custom template should be in current instance
            assert "memory_template" in tm.list_templates()

            # But a new instance should not have it
            tm2 = TemplateManager(pm)
            assert "memory_template" not in tm2.list_templates()


@pytest.mark.unit
class TestGetTemplateRecommendations:
    """Tests for template recommendations."""

    def test_recommend_by_file_types_development(self):
        """Test development template is recommended for code files."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            recommendations = tm.get_template_recommendations(file_types=[".py", ".js"])

            assert "development" in recommendations

    def test_recommend_by_file_types_photography(self):
        """Test photography template is recommended for image files."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            recommendations = tm.get_template_recommendations(
                file_types=[".jpg", ".raw", ".cr2"]
            )

            assert "photography" in recommendations

    def test_recommend_by_file_types_work(self):
        """Test work template is recommended for office documents."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            recommendations = tm.get_template_recommendations(
                file_types=[".pdf", ".docx", ".xlsx"]
            )

            assert "work" in recommendations

    def test_recommend_by_use_case_work(self):
        """Test work template is recommended for work use case."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            recommendations = tm.get_template_recommendations(
                use_case="organizing business documents"
            )

            assert "work" in recommendations

    def test_recommend_by_use_case_personal(self):
        """Test personal template is recommended for personal use case."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            recommendations = tm.get_template_recommendations(
                use_case="personal family photos"
            )

            assert "personal" in recommendations

    def test_recommend_by_use_case_development(self):
        """Test development template is recommended for coding."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            recommendations = tm.get_template_recommendations(
                use_case="software development projects"
            )

            assert "development" in recommendations

    def test_recommend_by_use_case_photography(self):
        """Test photography template is recommended for photography."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            recommendations = tm.get_template_recommendations(
                use_case="photo shoot organization camera files"
            )

            assert "photography" in recommendations

    def test_recommend_by_use_case_academic(self):
        """Test academic template is recommended for academic work."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            recommendations = tm.get_template_recommendations(
                use_case="university research and study"
            )

            assert "academic" in recommendations

    def test_recommendations_remove_duplicates(self):
        """Test that recommendations don't contain duplicates."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            recommendations = tm.get_template_recommendations(
                file_types=[".py", ".java"],
                use_case="development programming",
            )

            assert len(recommendations) == len(set(recommendations))

    def test_recommendations_empty_when_no_match(self):
        """Test empty recommendations when no criteria match."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            recommendations = tm.get_template_recommendations(file_types=[".txt"])

            assert isinstance(recommendations, list)
            assert len(recommendations) == 0


@pytest.mark.unit
class TestCompareTemplates:
    """Tests for template comparison."""

    def test_compare_two_templates(self):
        """Test comparing two templates."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            comparison = tm.compare_templates(["work", "personal"])

            assert comparison is not None
            assert "templates" in comparison
            assert len(comparison["templates"]) == 2

    def test_compare_templates_includes_metadata(self):
        """Test that comparison includes template metadata."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            comparison = tm.compare_templates(["photography", "development"])

            for template in comparison["templates"]:
                assert "name" in template
                assert "description" in template
                assert "naming_style" in template
                assert "folder_structure" in template
                assert "num_folder_mappings" in template
                assert "num_category_overrides" in template

    def test_compare_templates_less_than_two_invalid(self):
        """Test comparing with less than 2 valid templates returns None."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            comparison = tm.compare_templates(["nonexistent"])

            assert comparison is None

    def test_compare_multiple_templates(self):
        """Test comparing more than two templates."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            comparison = tm.compare_templates(
                ["work", "personal", "photography", "development"]
            )

            assert comparison is not None
            assert len(comparison["templates"]) == 4

    def test_compare_templates_skips_nonexistent(self):
        """Test that comparison skips non-existent templates."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            comparison = tm.compare_templates(["work", "nonexistent", "personal"])

            assert comparison is not None
            assert len(comparison["templates"]) == 2


@pytest.mark.unit
class TestTemplateDataIntegrity:
    """Tests for template data integrity and consistency."""

    def test_all_templates_have_required_fields(self):
        """Test that all templates have required fields."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            for template_name in tm.list_templates():
                template = tm.get_template(template_name)
                assert "name" in template
                assert "description" in template
                assert "preferences" in template
                assert "learned_patterns" in template
                assert "confidence_data" in template

    def test_all_templates_have_global_preferences(self):
        """Test that all templates have global preferences structure."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            for template_name in tm.list_templates():
                template = tm.get_template(template_name)
                prefs = template["preferences"]
                assert "global" in prefs
                global_prefs = prefs["global"]
                assert "naming_patterns" in global_prefs
                assert "folder_mappings" in global_prefs
                assert "category_overrides" in global_prefs

    def test_all_confidence_values_valid(self):
        """Test that all confidence values are between 0 and 1."""
        with TemporaryDirectory() as tmpdir:
            pm = ProfileManager(storage_path=tmpdir)
            tm = TemplateManager(pm)

            for template_name in tm.list_templates():
                template = tm.get_template(template_name)
                for key, value in template["confidence_data"].items():
                    assert 0 <= value <= 1, f"Invalid confidence for {key}: {value}"
