"""Extended tests for file_organizer.services.intelligence.profile_manager.

Covers Profile validation edge cases, ProfileManager CRUD operations,
sanitization, atomic writes, thread safety, and error handling for
missed coverage lines.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from file_organizer.services.intelligence.profile_manager import Profile, ProfileManager

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Profile dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProfileValidation:
    """Test Profile.validate edge cases."""

    def test_valid_profile(self):
        p = Profile(profile_name="test", description="A test profile")
        assert p.validate() is True

    def test_empty_name_invalid(self):
        p = Profile(profile_name="", description="desc")
        assert p.validate() is False

    def test_empty_description_invalid(self):
        p = Profile(profile_name="test", description="")
        assert p.validate() is False

    def test_name_not_string_invalid(self):
        p = Profile(profile_name=123, description="desc")  # type: ignore[arg-type]
        assert p.validate() is False

    def test_bad_timestamp_invalid(self):
        p = Profile(profile_name="test", description="desc", created="not-a-date")
        assert p.validate() is False

    def test_bad_preferences_structure(self):
        p = Profile(profile_name="test", description="desc")
        p.preferences = {"only_global": {}}  # missing directory_specific
        assert p.validate() is False

    def test_preferences_not_dict(self):
        p = Profile(profile_name="test", description="desc")
        p.preferences = "bad"  # type: ignore[assignment]
        assert p.validate() is False

    def test_from_dict_defaults(self):
        p = Profile.from_dict({})
        assert p.profile_name == "default"
        assert p.description == ""

    def test_to_dict_roundtrip(self):
        p = Profile(profile_name="round", description="trip")
        d = p.to_dict()
        p2 = Profile.from_dict(d)
        assert p2.profile_name == "round"
        assert p2.description == "trip"


# ---------------------------------------------------------------------------
# ProfileManager — sanitize
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSanitizeProfileName:
    """Test _sanitize_profile_name."""

    def test_normal_name(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        assert pm._sanitize_profile_name("my_profile") == "my_profile"

    def test_invalid_chars_replaced(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        result = pm._sanitize_profile_name('a<b>c:d"e')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result

    def test_dots_and_spaces_stripped(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        result = pm._sanitize_profile_name("  ..name..  ")
        assert result == "name"

    def test_empty_becomes_profile(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        result = pm._sanitize_profile_name("...")
        assert result == "profile"


# ---------------------------------------------------------------------------
# ProfileManager — create / activate / delete
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProfileManagerCRUD:
    """Test ProfileManager CRUD operations."""

    def test_default_profile_created(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        assert pm.profile_exists("default")

    def test_create_profile(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        p = pm.create_profile("work", "Work profile")
        assert p is not None
        assert p.profile_name == "work"
        assert pm.profile_exists("work")

    def test_create_duplicate_returns_none(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        pm.create_profile("dup", "first")
        result = pm.create_profile("dup", "second")
        assert result is None

    def test_create_invalid_data(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        # Profile with empty name after sanitization
        # Force invalid by patching validate to return False
        with patch.object(Profile, "validate", return_value=False):
            result = pm.create_profile("bad", "bad profile")
        assert result is None

    def test_activate_profile(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        pm.create_profile("work", "Work")
        assert pm.activate_profile("work") is True
        active = pm.get_active_profile()
        assert active is not None
        assert active.profile_name == "work"

    def test_activate_nonexistent(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        assert pm.activate_profile("nonexistent") is False

    def test_delete_profile(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        pm.create_profile("todelete", "will be deleted")
        assert pm.delete_profile("todelete") is True
        assert not pm.profile_exists("todelete")

    def test_delete_default_fails(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        assert pm.delete_profile("default") is False

    def test_delete_nonexistent(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        assert pm.delete_profile("nope") is False

    def test_delete_active_without_force(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        pm.create_profile("active", "Active one")
        pm.activate_profile("active")
        assert pm.delete_profile("active", force=False) is False

    def test_delete_active_with_force(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        pm.create_profile("active", "Active one")
        pm.activate_profile("active")
        assert pm.delete_profile("active", force=True) is True
        # Should have switched to default
        active = pm.get_active_profile()
        assert active is not None
        assert active.profile_name == "default"


# ---------------------------------------------------------------------------
# ProfileManager — update / get / list / count
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProfileManagerOperations:
    """Test update, get, list, count operations."""

    def test_update_description(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        pm.create_profile("up", "original")
        assert pm.update_profile("up", description="updated") is True
        p = pm.get_profile("up")
        assert p is not None
        assert p.description == "updated"

    def test_update_preferences(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        pm.create_profile("up", "for prefs")
        new_prefs = {"global": {"theme": "dark"}, "directory_specific": {}}
        assert pm.update_profile("up", preferences=new_prefs) is True
        p = pm.get_profile("up")
        assert p is not None
        assert p.preferences["global"]["theme"] == "dark"

    def test_update_nonexistent(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        assert pm.update_profile("nope", description="x") is False

    def test_update_invalid_after_update(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        pm.create_profile("up", "valid")
        # Provide preferences that will cause validation to fail
        bad_prefs = {"only_global": {}}  # missing directory_specific
        assert pm.update_profile("up", preferences=bad_prefs) is False

    def test_get_profile(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        p = pm.get_profile("default")
        assert p is not None
        assert p.profile_name == "default"

    def test_get_nonexistent_profile(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        assert pm.get_profile("nope") is None

    def test_list_profiles(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        pm.create_profile("alpha", "A")
        pm.create_profile("beta", "B")
        profiles = pm.list_profiles()
        names = [p.profile_name for p in profiles]
        assert "default" in names
        assert "alpha" in names
        assert "beta" in names

    def test_get_profile_count(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        pm.create_profile("extra", "Extra")
        assert pm.get_profile_count() >= 2  # default + extra


# ---------------------------------------------------------------------------
# ProfileManager — error handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProfileManagerErrors:
    """Test error handling paths."""

    def test_load_corrupted_json(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        # Write bad JSON to a profile file
        bad_path = tmp_path / "profiles" / "bad.json"
        bad_path.write_text("{{{NOT JSON")
        assert pm._load_profile_from_disk("bad") is None

    def test_load_invalid_profile_structure(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        # Write valid JSON but invalid profile data
        bad_path = tmp_path / "profiles" / "inv.json"
        bad_path.write_text(json.dumps({"profile_name": "", "description": ""}))
        assert pm._load_profile_from_disk("inv") is None

    def test_save_error_returns_false(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        p = Profile(profile_name="fail", description="fail save")
        with patch("builtins.open", side_effect=PermissionError("denied")):
            assert pm._save_profile_to_disk(p) is False

    def test_get_active_profile_name_error(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        with patch("builtins.open", side_effect=OSError("read fail")):
            result = pm._get_active_profile_name()
        assert result == "default"

    def test_set_active_profile_name_error(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        with patch("builtins.open", side_effect=OSError("write fail")):
            assert pm._set_active_profile_name("x") is False

    def test_update_learned_patterns_and_confidence(self, tmp_path):
        pm = ProfileManager(storage_path=tmp_path / "profiles")
        pm.create_profile("lp", "patterns")
        result = pm.update_profile(
            "lp",
            learned_patterns={"ext:.txt": 5},
            confidence_data={"overall": 0.9},
        )
        assert result is True
        p = pm.get_profile("lp")
        assert p is not None
        assert p.learned_patterns == {"ext:.txt": 5}
        assert p.confidence_data == {"overall": 0.9}
