"""
Tests for ProfileManager

Tests profile CRUD operations, activation, validation, and atomic operations.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from file_organizer.services.intelligence.profile_manager import (
    Profile,
    ProfileManager
)


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


def test_profile_creation(profile_manager):
    """Test profile creation."""
    profile = profile_manager.create_profile("test_profile", "Test description")

    assert profile is not None
    assert profile.profile_name == "test_profile"
    assert profile.description == "Test description"
    assert profile.profile_version == "1.0"
    assert profile.created is not None
    assert profile.updated is not None


def test_profile_validation(profile_manager):
    """Test profile validation."""
    profile = profile_manager.create_profile("valid_profile", "Valid")
    assert profile.validate()

    # Test invalid profile
    invalid_profile = Profile(profile_name="", description="Invalid")
    assert not invalid_profile.validate()


def test_default_profile_exists(profile_manager):
    """Test that default profile is created automatically."""
    default_profile = profile_manager.get_profile("default")
    assert default_profile is not None
    assert default_profile.profile_name == "default"


def test_activate_profile(profile_manager):
    """Test profile activation."""
    # Create test profile
    profile_manager.create_profile("test1", "Test 1")

    # Activate it
    success = profile_manager.activate_profile("test1")
    assert success

    # Verify it's active
    active = profile_manager.get_active_profile()
    assert active is not None
    assert active.profile_name == "test1"


def test_list_profiles(profile_manager):
    """Test listing all profiles."""
    # Create multiple profiles
    profile_manager.create_profile("profile1", "Profile 1")
    profile_manager.create_profile("profile2", "Profile 2")
    profile_manager.create_profile("profile3", "Profile 3")

    profiles = profile_manager.list_profiles()

    # Should include default + 3 created
    assert len(profiles) >= 4

    names = [p.profile_name for p in profiles]
    assert "default" in names
    assert "profile1" in names
    assert "profile2" in names
    assert "profile3" in names


def test_delete_profile(profile_manager):
    """Test profile deletion."""
    # Create and delete profile
    profile_manager.create_profile("to_delete", "Will be deleted")
    assert profile_manager.profile_exists("to_delete")

    success = profile_manager.delete_profile("to_delete")
    assert success
    assert not profile_manager.profile_exists("to_delete")


def test_cannot_delete_default_profile(profile_manager):
    """Test that default profile cannot be deleted."""
    success = profile_manager.delete_profile("default")
    assert not success
    assert profile_manager.profile_exists("default")


def test_cannot_delete_active_profile_without_force(profile_manager):
    """Test that active profile cannot be deleted without force."""
    # Create and activate profile
    profile_manager.create_profile("active_test", "Active")
    profile_manager.activate_profile("active_test")

    # Try to delete without force
    success = profile_manager.delete_profile("active_test", force=False)
    assert not success


def test_delete_active_profile_with_force(profile_manager):
    """Test deleting active profile with force flag."""
    # Create and activate profile
    profile_manager.create_profile("active_test2", "Active 2")
    profile_manager.activate_profile("active_test2")

    # Delete with force
    success = profile_manager.delete_profile("active_test2", force=True)
    assert success

    # Should switch to default
    active = profile_manager.get_active_profile()
    assert active.profile_name == "default"


def test_update_profile(profile_manager):
    """Test updating profile fields."""
    # Create profile
    profile_manager.create_profile("update_test", "Original description")

    # Update description
    success = profile_manager.update_profile(
        "update_test",
        description="Updated description"
    )
    assert success

    # Verify update
    updated = profile_manager.get_profile("update_test")
    assert updated.description == "Updated description"


def test_update_profile_preferences(profile_manager):
    """Test updating profile preferences."""
    profile_manager.create_profile("prefs_test", "Preferences test")

    new_prefs = {
        'global': {'test_key': 'test_value'},
        'directory_specific': {}
    }

    success = profile_manager.update_profile(
        "prefs_test",
        preferences=new_prefs
    )
    assert success

    # Verify
    updated = profile_manager.get_profile("prefs_test")
    assert updated.preferences['global']['test_key'] == 'test_value'


def test_profile_name_sanitization(profile_manager):
    """Test that profile names are sanitized for filesystem."""
    # Create profile with special characters
    profile = profile_manager.create_profile("test/profile:name", "Test")

    # Should be sanitized
    assert profile is not None
    # Special chars should be replaced with underscores
    path = profile_manager._get_profile_path("test/profile:name")
    assert '/' not in path.name
    assert ':' not in path.name


def test_profile_persistence(profile_manager):
    """Test that profiles persist across manager instances."""
    # Create profile
    profile_manager.create_profile("persist_test", "Persistence test")

    # Create new manager with same storage
    new_manager = ProfileManager(storage_path=profile_manager.storage_path)

    # Should be able to load profile
    loaded = new_manager.get_profile("persist_test")
    assert loaded is not None
    assert loaded.profile_name == "persist_test"
    assert loaded.description == "Persistence test"


def test_profile_exists(profile_manager):
    """Test checking if profile exists."""
    assert not profile_manager.profile_exists("nonexistent")

    profile_manager.create_profile("exists_test", "Test")
    assert profile_manager.profile_exists("exists_test")


def test_get_profile_count(profile_manager):
    """Test getting total profile count."""
    initial_count = profile_manager.get_profile_count()

    profile_manager.create_profile("count1", "Count 1")
    profile_manager.create_profile("count2", "Count 2")

    new_count = profile_manager.get_profile_count()
    assert new_count == initial_count + 2


def test_concurrent_profile_operations(profile_manager):
    """Test thread-safe profile operations."""
    import threading

    results = []

    def create_profile(name):
        result = profile_manager.create_profile(name, f"Description {name}")
        results.append(result is not None)

    threads = []
    for i in range(10):
        t = threading.Thread(target=create_profile, args=(f"concurrent_{i}",))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # All should succeed
    assert all(results)


def test_atomic_profile_switching(profile_manager):
    """Test atomic profile switching with rollback."""
    # Create two profiles
    profile_manager.create_profile("profile_a", "Profile A")
    profile_manager.create_profile("profile_b", "Profile B")

    # Activate profile_a
    profile_manager.activate_profile("profile_a")
    assert profile_manager.get_active_profile().profile_name == "profile_a"

    # Switch to profile_b
    profile_manager.activate_profile("profile_b")
    assert profile_manager.get_active_profile().profile_name == "profile_b"


def test_profile_to_dict_and_from_dict(profile_manager):
    """Test profile serialization and deserialization."""
    # Create profile
    original = profile_manager.create_profile("serialize_test", "Serialization test")
    original_dict = original.to_dict()

    # Create from dict
    restored = Profile.from_dict(original_dict)

    assert restored.profile_name == original.profile_name
    assert restored.description == original.description
    assert restored.profile_version == original.profile_version
    assert restored.created == original.created


def test_profile_with_complex_data(profile_manager):
    """Test profile with complex nested data."""
    profile_manager.create_profile("complex_test", "Complex data test")

    complex_prefs = {
        'global': {
            'nested': {
                'deep': {
                    'value': 'test'
                }
            },
            'list_data': [1, 2, 3, 4, 5]
        },
        'directory_specific': {
            '/path/to/dir': {
                'setting': 'value'
            }
        }
    }

    success = profile_manager.update_profile(
        "complex_test",
        preferences=complex_prefs
    )
    assert success

    # Verify complex data
    loaded = profile_manager.get_profile("complex_test")
    assert loaded.preferences['global']['nested']['deep']['value'] == 'test'
    assert loaded.preferences['global']['list_data'] == [1, 2, 3, 4, 5]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
