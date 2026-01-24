"""
Tests for ProfileExporter and ProfileImporter

Tests export/import functionality, validation, and selective operations.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from file_organizer.services.intelligence.profile_exporter import ProfileExporter
from file_organizer.services.intelligence.profile_importer import ProfileImporter
from file_organizer.services.intelligence.profile_manager import ProfileManager


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
def exporter(profile_manager):
    """Create ProfileExporter."""
    return ProfileExporter(profile_manager)


@pytest.fixture
def importer(profile_manager):
    """Create ProfileImporter."""
    return ProfileImporter(profile_manager)


@pytest.fixture
def sample_profile(profile_manager):
    """Create a sample profile with data."""
    profile_manager.create_profile("sample", "Sample profile")

    # Add some data
    profile_manager.update_profile(
        "sample",
        preferences={
            'global': {
                'test_setting': 'test_value',
                'naming_patterns': {'pattern1': 'value1'}
            },
            'directory_specific': {
                '/test/path': {'setting': 'value'}
            }
        },
        learned_patterns={'pattern_type': 'learned_value'},
        confidence_data={'setting1': 0.85}
    )

    return profile_manager.get_profile("sample")


# ============================================================================
# ProfileExporter Tests
# ============================================================================

def test_export_profile(exporter, sample_profile, temp_storage):
    """Test exporting a profile."""
    output_file = temp_storage / "export.json"

    success = exporter.export_profile("sample", output_file)
    assert success
    assert output_file.exists()

    # Verify exported data
    with open(output_file) as f:
        data = json.load(f)

    assert data['profile_name'] == "sample"
    assert data['description'] == "Sample profile"
    assert 'exported_at' in data
    assert 'preferences' in data


def test_export_nonexistent_profile(exporter, temp_storage):
    """Test exporting a profile that doesn't exist."""
    output_file = temp_storage / "export.json"

    success = exporter.export_profile("nonexistent", output_file)
    assert not success


def test_export_selective(exporter, sample_profile, temp_storage):
    """Test selective export."""
    output_file = temp_storage / "selective_export.json"

    success = exporter.export_selective(
        "sample",
        output_file,
        ['global', 'learned_patterns']
    )
    assert success
    assert output_file.exists()

    # Verify selective export
    with open(output_file) as f:
        data = json.load(f)

    assert data['export_type'] == 'selective'
    assert 'included_preferences' in data
    assert 'global' in data['included_preferences']
    assert 'preferences' in data


def test_validate_export(exporter, sample_profile, temp_storage):
    """Test export validation."""
    output_file = temp_storage / "export.json"
    exporter.export_profile("sample", output_file)

    # Validate exported file
    is_valid = exporter.validate_export(output_file)
    assert is_valid


def test_preview_export(exporter, sample_profile):
    """Test export preview."""
    preview = exporter.preview_export("sample")

    assert preview is not None
    assert preview['profile_name'] == "sample"
    assert 'statistics' in preview
    assert 'export_size_estimate' in preview


def test_export_multiple_profiles(exporter, profile_manager, temp_storage):
    """Test exporting multiple profiles."""
    # Create multiple profiles
    profile_manager.create_profile("profile1", "Profile 1")
    profile_manager.create_profile("profile2", "Profile 2")

    output_dir = temp_storage / "exports"

    results = exporter.export_multiple(
        ["profile1", "profile2"],
        output_dir
    )

    assert results["profile1"] is True
    assert results["profile2"] is True
    assert (output_dir / "profile1.json").exists()
    assert (output_dir / "profile2.json").exists()


# ============================================================================
# ProfileImporter Tests
# ============================================================================

def test_import_profile(exporter, importer, sample_profile, temp_storage):
    """Test importing a profile."""
    # Export first
    export_file = temp_storage / "export.json"
    exporter.export_profile("sample", export_file)

    # Delete original
    importer.profile_manager.delete_profile("sample", force=True)

    # Import
    imported = importer.import_profile(export_file, "imported_sample")

    assert imported is not None
    assert imported.profile_name == "imported_sample"
    assert imported.description == "Sample profile"


def test_validate_import_file(exporter, importer, sample_profile, temp_storage):
    """Test import file validation."""
    # Export profile
    export_file = temp_storage / "export.json"
    exporter.export_profile("sample", export_file)

    # Validate
    validation = importer.validate_import_file(export_file)

    assert validation.valid
    assert len(validation.errors) == 0
    assert validation.profile_data is not None


def test_validate_invalid_import_file(importer, temp_storage):
    """Test validation of invalid import file."""
    # Create invalid file
    invalid_file = temp_storage / "invalid.json"
    with open(invalid_file, 'w') as f:
        json.dump({'invalid': 'data'}, f)

    validation = importer.validate_import_file(invalid_file)

    assert not validation.valid
    assert len(validation.errors) > 0


def test_preview_import(exporter, importer, sample_profile, temp_storage):
    """Test import preview."""
    # Export profile
    export_file = temp_storage / "export.json"
    exporter.export_profile("sample", export_file)

    # Preview import
    preview = importer.preview_import(export_file)

    assert preview is not None
    assert preview['profile_name'] == "sample"
    assert 'preferences_count' in preview
    assert 'validation' in preview


def test_import_with_name_conflict(exporter, importer, sample_profile, temp_storage):
    """Test importing with conflicting name."""
    # Export profile
    export_file = temp_storage / "export.json"
    exporter.export_profile("sample", export_file)

    # Try to import with same name (should backup and overwrite)
    imported = importer.import_profile(export_file, "sample")

    assert imported is not None
    assert imported.profile_name == "sample"


def test_import_selective(exporter, importer, sample_profile, temp_storage):
    """Test selective import."""
    # Export profile
    export_file = temp_storage / "export.json"
    exporter.export_profile("sample", export_file)

    # Create new profile
    importer.profile_manager.create_profile("target", "Target profile")

    # Import selective preferences
    imported = importer.import_selective(
        export_file,
        ['global'],
        "target"
    )

    assert imported is not None
    assert imported.profile_name == "target"


def test_export_import_roundtrip(exporter, importer, sample_profile, temp_storage):
    """Test complete export/import roundtrip."""
    # Export
    export_file = temp_storage / "roundtrip.json"
    success = exporter.export_profile("sample", export_file)
    assert success

    # Get original data
    original = importer.profile_manager.get_profile("sample")
    original_prefs = original.preferences

    # Delete original
    importer.profile_manager.delete_profile("sample", force=True)

    # Import
    imported = importer.import_profile(export_file, "sample")

    assert imported is not None
    assert imported.profile_name == original.profile_name
    assert imported.description == original.description

    # Compare preferences
    assert imported.preferences['global'] == original_prefs['global']


def test_import_with_migration_needed(importer, temp_storage):
    """Test importing file that needs migration."""
    # Create export file with old version
    old_export = temp_storage / "old_export.json"
    old_data = {
        'profile_name': 'old_profile',
        'profile_version': '1.0',  # Current version
        'description': 'Old profile',
        'exported_at': '2024-01-01T00:00:00Z',
        'preferences': {
            'global': {},
            'directory_specific': {}
        },
        'learned_patterns': {},
        'confidence_data': {}
    }

    with open(old_export, 'w') as f:
        json.dump(old_data, f)

    # Import should work
    imported = importer.import_profile(old_export)
    assert imported is not None


def test_backup_on_overwrite(exporter, importer, sample_profile, temp_storage):
    """Test that backup is created when overwriting existing profile."""
    # Export profile
    export_file = temp_storage / "export.json"
    exporter.export_profile("sample", export_file)

    # Import over existing (should create backup)
    imported = importer.import_profile(export_file, "sample")

    assert imported is not None

    # Check backup directory exists
    backup_dir = importer.profile_manager.storage_path / "backups"
    assert backup_dir.exists()


def test_import_corrupted_file(importer, temp_storage):
    """Test importing corrupted JSON file."""
    # Create corrupted file
    corrupted = temp_storage / "corrupted.json"
    with open(corrupted, 'w') as f:
        f.write("{corrupted json content")

    validation = importer.validate_import_file(corrupted)
    assert not validation.valid


def test_import_large_profile(exporter, importer, profile_manager, temp_storage):
    """Test importing large profile."""
    # Create profile with lots of data
    profile_manager.create_profile("large", "Large profile")

    large_prefs = {
        'global': {f'key_{i}': f'value_{i}' for i in range(1000)},
        'directory_specific': {f'/path/{i}': {'data': i} for i in range(100)}
    }

    profile_manager.update_profile("large", preferences=large_prefs)

    # Export
    export_file = temp_storage / "large_export.json"
    success = exporter.export_profile("large", export_file)
    assert success

    # Delete and import
    profile_manager.delete_profile("large", force=True)
    imported = importer.import_profile(export_file, "large")

    assert imported is not None
    assert len(imported.preferences['global']) == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
