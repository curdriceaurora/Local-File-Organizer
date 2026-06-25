"""Integration tests for services/intelligence/profile_migrator.py.

Covers the uncovered integration-test branches:
- _get_current_timestamp (line 52)
- migrate_version backup-fails path (line 82)
- migrate_version exception handler (lines 87-89)
- _create_backup_if_requested failure path (lines 117-120)
- _execute_migration: no migration path found (lines 139-136)
- _apply_migration_steps: step function missing (lines 161-169)
- _apply_migration_steps: step function raises (lines 171-177)
- _update_migration_metadata (lines 185-195)
- _validate_and_save_migrated_profile: validation failure (lines 202-207)
- _validate_and_save_migrated_profile: save success (lines 210-231)
- backup_before_migration: exception path (lines 283-285)
- rollback_migration: backup not found (lines 302-304)
- rollback_migration: invalid backup data (lines 313-315)
- rollback_migration: success (lines 326-329)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def profile_manager(tmp_path: Path):
    """Real ProfileManager backed by a temp directory."""
    from file_organizer.services.intelligence.profile_manager import ProfileManager

    return ProfileManager(storage_path=tmp_path / "profiles")


@pytest.fixture
def migrator(profile_manager):
    """ProfileMigrator using the real ProfileManager."""
    from file_organizer.services.intelligence.profile_migrator import ProfileMigrator

    return ProfileMigrator(profile_manager)


@pytest.fixture
def sample_profile(profile_manager):
    """Create and return a real profile at version 1.0."""
    profile = profile_manager.create_profile("test_profile", "A test profile")
    assert profile is not None
    return profile


# ---------------------------------------------------------------------------
# _get_current_timestamp  (line 52)
# ---------------------------------------------------------------------------


@pytest.mark.ci
def test_get_current_timestamp_returns_iso_string(migrator) -> None:
    """_get_current_timestamp returns a non-empty ISO-format string."""
    ts = migrator._get_current_timestamp()
    assert isinstance(ts, str)
    assert "T" in ts  # ISO 8601 separator
    assert ts.endswith("Z")


# ---------------------------------------------------------------------------
# migrate_version: profile not found, unsupported version, already at target
# ---------------------------------------------------------------------------


@pytest.mark.ci
def test_migrate_version_profile_not_found(migrator) -> None:
    """migrate_version returns False when profile does not exist."""
    result = migrator.migrate_version("no_such_profile", "1.0")
    assert result is False


@pytest.mark.ci
def test_migrate_version_unsupported_target(migrator, sample_profile) -> None:
    """migrate_version returns False for unsupported target version."""
    result = migrator.migrate_version("test_profile", "99.0")
    assert result is False


@pytest.mark.ci
def test_migrate_version_already_at_target(migrator, sample_profile) -> None:
    """migrate_version returns True without migrating when version matches."""
    # Profile is already at 1.0; target is also 1.0
    result = migrator.migrate_version("test_profile", "1.0")
    assert result is True


# ---------------------------------------------------------------------------
# migrate_version: backup fails → line 82 (backup requested but path is None)
# ---------------------------------------------------------------------------


@pytest.mark.ci
def test_migrate_version_backup_fails_returns_false(migrator, sample_profile) -> None:
    """When backup is requested but backup_before_migration returns None, returns False.

    Exercises line 82: ``if backup and backup_path is None: return False``.
    We need a profile at a version different from 1.0, with backup=True,
    where backup_before_migration fails.
    """
    # Set profile version to "0.5" so migration IS needed (0.5 ≠ 1.0)
    migrator.profile_manager.update_profile("test_profile", profile_version="0.5")

    # Patch backup_before_migration to simulate failure
    with patch.object(migrator, "backup_before_migration", return_value=None):
        result = migrator.migrate_version("test_profile", "1.0", backup=True)

    assert result is False


# ---------------------------------------------------------------------------
# migrate_version: exception inside the try block (lines 87-89)
# ---------------------------------------------------------------------------


@pytest.mark.ci
def test_migrate_version_exception_returns_false(migrator) -> None:
    """An unexpected exception in migrate_version is caught and returns False."""

    def _raise(*_a, **_kw):
        raise RuntimeError("unexpected internal error")

    with patch.object(migrator, "_load_profile", side_effect=_raise):
        result = migrator.migrate_version("test_profile", "1.0")

    assert result is False


# ---------------------------------------------------------------------------
# _create_backup_if_requested: backup_before_migration returns None (lines 117-120)
# ---------------------------------------------------------------------------


@pytest.mark.ci
def test_create_backup_if_requested_returns_none_on_failure(migrator, sample_profile) -> None:
    """_create_backup_if_requested returns None when backup_before_migration fails."""
    with patch.object(migrator, "backup_before_migration", return_value=None):
        result = migrator._create_backup_if_requested(sample_profile, backup=True)

    assert result is None


@pytest.mark.ci
def test_create_backup_if_requested_skipped_when_backup_false(migrator, sample_profile) -> None:
    """_create_backup_if_requested returns None immediately when backup=False."""
    result = migrator._create_backup_if_requested(sample_profile, backup=False)
    assert result is None


# ---------------------------------------------------------------------------
# _execute_migration: no migration path (line 135)
# ---------------------------------------------------------------------------


@pytest.mark.ci
def test_execute_migration_no_path_returns_false(migrator, sample_profile) -> None:
    """_execute_migration returns False when _find_migration_path returns None.

    Uses a Profile object whose version is "0.5" (not in SUPPORTED_VERSIONS),
    so _find_migration_path("0.5", "1.0") returns None (no path defined).
    """
    from file_organizer.services.intelligence.profile_manager import Profile

    # Construct a Profile with version "0.5" — different from "1.0"
    old_profile = Profile(
        profile_name="test_profile",
        description="Old version profile",
        profile_version="0.5",
    )
    # _find_migration_path("0.5", "1.0") → None
    result = migrator._execute_migration("test_profile", old_profile, "1.0", None)
    assert result is False


# ---------------------------------------------------------------------------
# _apply_migration_steps: step function missing + exception (lines 161-177)
# ---------------------------------------------------------------------------


@pytest.mark.ci
def test_apply_migration_steps_missing_function_returns_none(migrator, sample_profile) -> None:
    """_apply_migration_steps returns None when the step key has no function."""
    migration_path = ["0.5->1.0"]  # no function registered for this step
    result = migrator._apply_migration_steps(sample_profile, migration_path, "test_profile", None)
    assert result is None


@pytest.mark.ci
def test_apply_migration_steps_function_raises_returns_none(migrator, sample_profile) -> None:
    """_apply_migration_steps returns None when migration function raises."""

    def _failing_step(_data):
        raise ValueError("migration error")

    migrator._migration_functions["0.5->1.0"] = _failing_step
    try:
        result = migrator._apply_migration_steps(sample_profile, ["0.5->1.0"], "test_profile", None)
        assert result is None
    finally:
        del migrator._migration_functions["0.5->1.0"]


# ---------------------------------------------------------------------------
# _update_migration_metadata  (lines 185-195)
# ---------------------------------------------------------------------------


@pytest.mark.ci
def test_update_migration_metadata_adds_history(migrator) -> None:
    """_update_migration_metadata stamps version and appends to migration_history."""
    data: dict = {"profile_version": "0.5"}
    updated = migrator._update_migration_metadata(data, "0.5", "1.0")
    assert updated["profile_version"] == "1.0"
    assert len(updated["migration_history"]) == 1
    assert updated["migration_history"][0]["from_version"] == "0.5"
    assert updated["migration_history"][0]["to_version"] == "1.0"


# ---------------------------------------------------------------------------
# backup_before_migration: success + exception path (lines 283-285)
# ---------------------------------------------------------------------------


@pytest.mark.ci
def test_backup_before_migration_success(migrator, sample_profile, tmp_path) -> None:
    """backup_before_migration writes a JSON file and returns its path."""
    backup_path = migrator.backup_before_migration(sample_profile)
    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.suffix == ".json"


@pytest.mark.ci
def test_backup_before_migration_exception_returns_none(migrator, sample_profile) -> None:
    """backup_before_migration catches exceptions and returns None (lines 283-285)."""
    # Patch Path.mkdir to raise OSError — deterministic, xdist-safe, no hardcoded paths.
    with patch("pathlib.Path.mkdir", side_effect=OSError("mkdir failed")):
        result = migrator.backup_before_migration(sample_profile)

    assert result is None


# ---------------------------------------------------------------------------
# rollback_migration  (lines 302-329)
# ---------------------------------------------------------------------------


@pytest.mark.ci
def test_rollback_migration_backup_not_found(migrator, tmp_path) -> None:
    """rollback_migration returns False when the backup file does not exist."""
    missing = tmp_path / "ghost_backup.json"
    result = migrator.rollback_migration("test_profile", missing)
    assert result is False


@pytest.mark.ci
def test_rollback_migration_success(migrator, sample_profile, tmp_path) -> None:
    """rollback_migration restores profile from valid backup file."""
    backup_path = migrator.backup_before_migration(sample_profile)
    assert backup_path is not None

    result = migrator.rollback_migration("test_profile", backup_path)
    assert result is True


# ---------------------------------------------------------------------------
# Full migration round-trip (lines 139-151, 202-231)
# Execute a migration where a real migration function is registered.
# ---------------------------------------------------------------------------


@pytest.mark.ci
def test_full_migration_roundtrip_with_registered_function(migrator, sample_profile) -> None:
    """End-to-end migration: register a step function, patch _find_migration_path
    to return a non-None path, exercise lines 139-151 and 202-231.
    """
    from unittest.mock import patch

    def _identity_migration(data: dict) -> dict:
        """No-op migration: returns data unchanged."""
        return dict(data)

    # Register the migration function for "0.5->1.0"
    migrator._migration_functions["0.5->1.0"] = _identity_migration

    try:
        # Patch _find_migration_path to return a path for "0.5" → "1.0"
        with patch.object(
            migrator,
            "_find_migration_path",
            return_value=["0.5->1.0"],
        ):
            from file_organizer.services.intelligence.profile_manager import Profile

            old_profile = Profile(
                profile_name="test_profile",
                description="Old version",
                profile_version="0.5",
            )
            result = migrator._execute_migration("test_profile", old_profile, "1.0", None)

        assert result is True
        # The profile should now be saved at version "1.0"
        updated = migrator.profile_manager.get_profile("test_profile")
        assert updated is not None
        assert updated.profile_version == "1.0"
    finally:
        del migrator._migration_functions["0.5->1.0"]
