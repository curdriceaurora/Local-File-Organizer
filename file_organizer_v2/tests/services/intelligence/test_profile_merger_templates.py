"""
Tests for ProfileMerger and TemplateManager

Tests profile merging, conflict resolution, and template operations.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from file_organizer.services.intelligence.profile_manager import ProfileManager
from file_organizer.services.intelligence.profile_merger import ProfileMerger
from file_organizer.services.intelligence.template_manager import TemplateManager


@pytest.fixture
def temp_storage():
    """Create temporary storage directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def profile_manager(temp_storage):
    """Create ProfileManager with temporary storage."""
    return ProfileManager(storage_path=temp_storage / "profiles")


@pytest.fixture
def merger(profile_manager):
    """Create ProfileMerger."""
    return ProfileMerger(profile_manager)


@pytest.fixture
def template_manager(profile_manager):
    """Create TemplateManager."""
    return TemplateManager(profile_manager)


@pytest.fixture
def sample_profiles(profile_manager):
    """Create sample profiles for merging."""
    # Profile 1
    profile_manager.create_profile("profile1", "Profile 1")
    profile_manager.update_profile(
        "profile1",
        preferences={
            'global': {
                'setting1': 'value1',
                'setting2': 'value2'
            },
            'directory_specific': {}
        },
        confidence_data={'setting1': 0.8, 'setting2': 0.7}
    )

    # Profile 2
    profile_manager.create_profile("profile2", "Profile 2")
    profile_manager.update_profile(
        "profile2",
        preferences={
            'global': {
                'setting1': 'value1_different',
                'setting3': 'value3'
            },
            'directory_specific': {}
        },
        confidence_data={'setting1': 0.9, 'setting3': 0.85}
    )

    return ["profile1", "profile2"]


# ============================================================================
# ProfileMerger Tests
# ============================================================================

def test_merge_profiles_basic(merger, sample_profiles):
    """Test basic profile merging."""
    merged = merger.merge_profiles(sample_profiles, "confident", "merged_test")

    assert merged is not None
    assert merged.profile_name == "merged_test"
    assert 'setting1' in merged.preferences['global']
    assert 'setting2' in merged.preferences['global']
    assert 'setting3' in merged.preferences['global']


def test_merge_with_confident_strategy(merger, sample_profiles):
    """Test merging with confident strategy."""
    merged = merger.merge_profiles(sample_profiles, "confident", "merged_confident")

    # setting1 should have value from profile2 (higher confidence: 0.9 vs 0.8)
    assert merged.preferences['global']['setting1'] == 'value1_different'


def test_merge_with_recent_strategy(merger, profile_manager, sample_profiles):
    """Test merging with recent strategy."""
    # Update profile2 to be more recent
    import time
    time.sleep(0.1)
    profile_manager.update_profile("profile2", description="Updated")

    merged = merger.merge_profiles(sample_profiles, "recent", "merged_recent")

    # Should prefer more recent profile's values
    assert merged is not None


def test_merge_with_first_strategy(merger, sample_profiles):
    """Test merging with first strategy."""
    merged = merger.merge_profiles(sample_profiles, "first", "merged_first")

    # setting1 should have value from first profile
    assert merged.preferences['global']['setting1'] == 'value1'


def test_merge_with_last_strategy(merger, sample_profiles):
    """Test merging with last strategy."""
    merged = merger.merge_profiles(sample_profiles, "last", "merged_last")

    # setting1 should have value from last profile
    assert merged.preferences['global']['setting1'] == 'value1_different'


def test_merge_requires_two_profiles(merger, profile_manager):
    """Test that merge requires at least 2 profiles."""
    profile_manager.create_profile("single", "Single profile")

    merged = merger.merge_profiles(["single"], "confident", "merged")
    assert merged is None


def test_merge_nonexistent_profile(merger):
    """Test merging with nonexistent profile."""
    merged = merger.merge_profiles(["nonexistent1", "nonexistent2"], "confident", "merged")
    assert merged is None


def test_get_merge_conflicts(merger, sample_profiles):
    """Test detecting merge conflicts."""
    conflicts = merger.get_merge_conflicts(sample_profiles)

    # setting1 has different values in both profiles
    assert 'global.setting1' in conflicts
    assert len(conflicts['global.setting1']) == 2


def test_merge_learned_patterns(merger, profile_manager):
    """Test merging learned patterns."""
    profile_manager.create_profile("patterns1", "Patterns 1")
    profile_manager.update_profile(
        "patterns1",
        learned_patterns={'pattern_a': 'value_a'},
        confidence_data={'pattern_a': 0.8}
    )

    profile_manager.create_profile("patterns2", "Patterns 2")
    profile_manager.update_profile(
        "patterns2",
        learned_patterns={'pattern_b': 'value_b'},
        confidence_data={'pattern_b': 0.9}
    )

    merged = merger.merge_profiles(["patterns1", "patterns2"], "confident", "merged_patterns")

    assert merged is not None
    assert 'pattern_a' in merged.learned_patterns
    assert 'pattern_b' in merged.learned_patterns


def test_merge_confidence_data(merger, profile_manager):
    """Test merging confidence data."""
    profile_manager.create_profile("conf1", "Confidence 1")
    profile_manager.update_profile(
        "conf1",
        confidence_data={'key1': 0.7, 'key2': 0.5}
    )

    profile_manager.create_profile("conf2", "Confidence 2")
    profile_manager.update_profile(
        "conf2",
        confidence_data={'key1': 0.9, 'key3': 0.8}
    )

    merged = merger.merge_profiles(["conf1", "conf2"], "confident", "merged_conf")

    # Should use highest confidence values
    assert merged.confidence_data['key1'] == 0.9  # max(0.7, 0.9)
    assert merged.confidence_data['key2'] == 0.5
    assert merged.confidence_data['key3'] == 0.8


def test_merge_overwrite_existing(merger, profile_manager, sample_profiles):
    """Test merging overwrites existing profile with same name."""
    # Create initial merged profile
    merger.merge_profiles(sample_profiles, "confident", "overwrite_test")

    # Merge again with same name (should overwrite)
    merged = merger.merge_profiles(sample_profiles, "first", "overwrite_test")

    assert merged is not None
    assert merged.profile_name == "overwrite_test"


# ============================================================================
# TemplateManager Tests
# ============================================================================

def test_list_templates(template_manager):
    """Test listing all templates."""
    templates = template_manager.list_templates()

    assert len(templates) == 5
    assert 'work' in templates
    assert 'personal' in templates
    assert 'photography' in templates
    assert 'development' in templates
    assert 'academic' in templates


def test_get_template(template_manager):
    """Test getting a template."""
    template = template_manager.get_template('work')

    assert template is not None
    assert template['name'] == 'Work Profile'
    assert 'preferences' in template
    assert 'learned_patterns' in template
    assert 'confidence_data' in template


def test_get_nonexistent_template(template_manager):
    """Test getting template that doesn't exist."""
    template = template_manager.get_template('nonexistent')
    assert template is None


def test_preview_template(template_manager):
    """Test template preview."""
    preview = template_manager.preview_template('photography')

    assert preview is not None
    assert preview['template_name'] == 'photography'
    assert preview['name'] == 'Photography Profile'
    assert 'preferences_summary' in preview
    assert 'learned_patterns' in preview
    assert 'confidence_levels' in preview


def test_create_profile_from_template(template_manager):
    """Test creating profile from template."""
    profile = template_manager.create_profile_from_template(
        'development',
        'my_dev_profile'
    )

    assert profile is not None
    assert profile.profile_name == 'my_dev_profile'
    assert len(profile.preferences['global']) > 0


def test_create_profile_from_template_already_exists(template_manager, profile_manager):
    """Test creating profile from template when name already exists."""
    # Create profile first
    profile_manager.create_profile('existing', 'Existing')

    # Try to create from template with same name
    profile = template_manager.create_profile_from_template('work', 'existing')
    assert profile is None


def test_create_profile_from_nonexistent_template(template_manager):
    """Test creating profile from nonexistent template."""
    profile = template_manager.create_profile_from_template(
        'nonexistent',
        'test_profile'
    )
    assert profile is None


def test_create_profile_with_customization(template_manager):
    """Test creating profile with customizations."""
    customize = {
        'description': 'Custom description',
        'naming_patterns': {'custom_pattern': 'custom_value'}
    }

    profile = template_manager.create_profile_from_template(
        'personal',
        'customized_profile',
        customize
    )

    assert profile is not None
    assert profile.description == 'Custom description'
    assert 'custom_pattern' in profile.preferences['global']['naming_patterns']


def test_all_templates_have_required_fields(template_manager):
    """Test that all templates have required fields."""
    templates = template_manager.list_templates()

    for template_name in templates:
        template = template_manager.get_template(template_name)

        assert 'name' in template
        assert 'description' in template
        assert 'preferences' in template
        assert 'learned_patterns' in template
        assert 'confidence_data' in template

        # Check preferences structure
        prefs = template['preferences']
        assert 'global' in prefs
        assert 'directory_specific' in prefs


def test_template_recommendations_by_file_types(template_manager):
    """Test getting template recommendations by file types."""
    # Python files
    recs = template_manager.get_template_recommendations(
        file_types=['.py', '.js'],
        use_case=None
    )
    assert 'development' in recs

    # Image files
    recs = template_manager.get_template_recommendations(
        file_types=['.jpg', '.raw'],
        use_case=None
    )
    assert 'photography' in recs

    # Document files
    recs = template_manager.get_template_recommendations(
        file_types=['.pdf', '.docx'],
        use_case=None
    )
    assert 'work' in recs or 'academic' in recs


def test_template_recommendations_by_use_case(template_manager):
    """Test getting template recommendations by use case."""
    # Work use case
    recs = template_manager.get_template_recommendations(
        file_types=None,
        use_case="corporate office work"
    )
    assert 'work' in recs

    # Photography use case
    recs = template_manager.get_template_recommendations(
        file_types=None,
        use_case="photo shoot camera"
    )
    assert 'photography' in recs

    # Development use case
    recs = template_manager.get_template_recommendations(
        file_types=None,
        use_case="software development coding"
    )
    assert 'development' in recs


def test_compare_templates(template_manager):
    """Test comparing multiple templates."""
    comparison = template_manager.compare_templates(['work', 'personal'])

    assert comparison is not None
    assert 'templates' in comparison
    assert len(comparison['templates']) == 2


def test_create_custom_template(template_manager, profile_manager):
    """Test creating custom template from profile."""
    # Create profile
    profile_manager.create_profile('custom_base', 'Custom base profile')
    profile_manager.update_profile(
        'custom_base',
        preferences={
            'global': {'custom_setting': 'custom_value'},
            'directory_specific': {}
        }
    )

    # Create template from it
    success = template_manager.create_custom_template('custom_base', 'my_custom_template')
    assert success

    # Verify template exists
    template = template_manager.get_template('my_custom_template')
    assert template is not None


def test_create_custom_template_from_nonexistent_profile(template_manager):
    """Test creating custom template from nonexistent profile."""
    success = template_manager.create_custom_template('nonexistent', 'custom_template')
    assert not success


def test_work_template_has_proper_structure(template_manager):
    """Test work template has proper structure."""
    template = template_manager.get_template('work')

    # Should have formal naming
    naming = template['preferences']['global']['naming_patterns']
    assert naming['case_style'] == 'title'
    assert naming['date_format'] == 'YYYY-MM-DD'

    # Should have work-related folders
    folders = template['preferences']['global']['folder_mappings']
    assert 'documents' in folders or 'reports' in folders


def test_photography_template_has_proper_structure(template_manager):
    """Test photography template has proper structure."""
    template = template_manager.get_template('photography')

    # Should have RAW handling
    folders = template['preferences']['global']['folder_mappings']
    assert 'raw' in folders

    # Should have event-based organization
    patterns = template['learned_patterns']
    assert patterns.get('organization_style') == 'event_based'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
