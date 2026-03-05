"""Coverage tests for ProfileManager — targets uncovered branches."""

from __future__ import annotations

import json

import pytest

from file_organizer.services.intelligence.profile_manager import (
    Profile,
    ProfileManager,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def pm(tmp_path):
    return ProfileManager(storage_path=tmp_path / "profiles")


# ---------------------------------------------------------------------------
# Profile dataclass
# ---------------------------------------------------------------------------


class TestProfile:
    def test_defaults_initialised(self):
        p = Profile(profile_name="test", description="desc")
        assert p.created is not None
        assert p.updated is not None
        assert p.preferences is not None
        assert p.learned_patterns is not None
        assert p.confidence_data is not None

    def test_to_dict_from_dict_roundtrip(self):
        p = Profile(profile_name="t", description="d")
        d = p.to_dict()
        p2 = Profile.from_dict(d)
        assert p2.profile_name == "t"

    def test_validate_valid(self):
        p = Profile(profile_name="t", description="d")
        assert p.validate() is True

    def test_validate_empty_name(self):
        p = Profile(profile_name="", description="d")
        assert p.validate() is False

    def test_validate_name_not_string(self):
        p = Profile(profile_name="t", description="d")
        p.profile_name = 123  # type: ignore[assignment]
        assert p.validate() is False

    def test_validate_bad_timestamp(self):
        p = Profile(profile_name="t", description="d")
        p.created = "not-a-date"
        assert p.validate() is False

    def test_validate_bad_preferences(self):
        p = Profile(profile_name="t", description="d")
        p.preferences = "not a dict"  # type: ignore[assignment]
        assert p.validate() is False

    def test_validate_missing_global_key(self):
        p = Profile(profile_name="t", description="d")
        p.preferences = {"directory_specific": {}}
        assert p.validate() is False


# ---------------------------------------------------------------------------
# ProfileManager — sanitize
# ---------------------------------------------------------------------------


class TestSanitize:
    def test_sanitize_invalid_chars(self, pm):
        result = pm._sanitize_profile_name('my<pro>file/"test"')
        assert "<" not in result
        assert ">" not in result

    def test_sanitize_empty_string(self, pm):
        result = pm._sanitize_profile_name("...")
        assert result == "profile"

    def test_sanitize_whitespace(self, pm):
        result = pm._sanitize_profile_name("  . name . ")
        assert result.strip() != ""


# ---------------------------------------------------------------------------
# create / list / delete / activate
# ---------------------------------------------------------------------------


class TestCRUD:
    def test_create_profile(self, pm):
        p = pm.create_profile("new_prof", "A new profile")
        assert p is not None
        assert p.profile_name == "new_prof"

    def test_create_duplicate(self, pm):
        pm.create_profile("dup", "first")
        result = pm.create_profile("dup", "second")
        assert result is None

    def test_list_profiles(self, pm):
        pm.create_profile("extra", "extra")
        profiles = pm.list_profiles()
        names = [p.profile_name for p in profiles]
        assert "default" in names
        assert "extra" in names

    def test_delete_profile(self, pm):
        pm.create_profile("to_del", "delete me")
        assert pm.delete_profile("to_del") is True
        assert pm.profile_exists("to_del") is False

    def test_delete_default_fails(self, pm):
        assert pm.delete_profile("default") is False

    def test_delete_nonexistent(self, pm):
        assert pm.delete_profile("nope") is False

    def test_delete_active_without_force(self, pm):
        pm.create_profile("act", "active")
        pm.activate_profile("act")
        assert pm.delete_profile("act", force=False) is False

    def test_delete_active_with_force(self, pm):
        pm.create_profile("act2", "active2")
        pm.activate_profile("act2")
        assert pm.delete_profile("act2", force=True) is True

    def test_activate_nonexistent(self, pm):
        assert pm.activate_profile("nope") is False

    def test_activate_and_verify(self, pm):
        pm.create_profile("myp", "my profile")
        assert pm.activate_profile("myp") is True
        active = pm.get_active_profile()
        assert active is not None
        assert active.profile_name == "myp"


# ---------------------------------------------------------------------------
# update_profile
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    def test_update_description(self, pm):
        pm.create_profile("upd", "original")
        assert pm.update_profile("upd", description="updated") is True
        p = pm.get_profile("upd")
        assert p is not None
        assert p.description == "updated"

    def test_update_preferences(self, pm):
        pm.create_profile("upd2", "desc")
        new_prefs = {"global": {"key": "val"}, "directory_specific": {}}
        assert pm.update_profile("upd2", preferences=new_prefs) is True

    def test_update_nonexistent(self, pm):
        assert pm.update_profile("nope", description="x") is False


# ---------------------------------------------------------------------------
# Load profile edge cases
# ---------------------------------------------------------------------------


class TestLoadProfile:
    def test_load_corrupted_json(self, pm):
        profile_path = pm._get_profile_path("bad")
        profile_path.write_text("{bad json", encoding="utf-8")
        assert pm._load_profile_from_disk("bad") is None

    def test_load_invalid_structure(self, pm):
        profile_path = pm._get_profile_path("bad2")
        profile_path.write_text(
            json.dumps({"profile_name": "", "description": "d"}), encoding="utf-8"
        )
        # Empty name fails validation
        assert pm._load_profile_from_disk("bad2") is None


# ---------------------------------------------------------------------------
# get_active_profile edge cases
# ---------------------------------------------------------------------------


class TestGetActiveProfile:
    def test_active_file_error(self, pm):
        # Corrupt the active profile file
        pm.active_profile_file.write_text("nonexistent_profile", encoding="utf-8")
        result = pm.get_active_profile()
        assert result is None  # Profile doesn't exist

    def test_get_profile_count(self, pm):
        pm.create_profile("extra", "e")
        count = pm.get_profile_count()
        assert count >= 2  # default + extra
