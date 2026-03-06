"""Tests for path migration from legacy locations."""

from file_organizer.config.path_migration import PathMigrator, detect_legacy_paths


def test_detect_legacy_paths_finds_old_locations(tmp_path):
    """Should detect all 3 legacy path patterns"""
    # Create mock legacy directories
    legacy_1 = tmp_path / ".file-organizer"
    legacy_2 = tmp_path / ".file_organizer"
    legacy_3 = tmp_path / ".config" / "file-organizer"

    legacy_1.mkdir()
    legacy_2.mkdir()
    legacy_3.mkdir(parents=True)

    detected = detect_legacy_paths(
        home=tmp_path, config_home=tmp_path / ".config", data_home=tmp_path / ".local" / "share"
    )

    assert legacy_1 in detected
    assert legacy_2 in detected
    assert legacy_3 in detected


def test_path_migrator_copies_legacy_files(tmp_path):
    """Should copy files from legacy to canonical locations"""
    # Setup legacy directory with files
    legacy = tmp_path / ".file-organizer"
    legacy.mkdir()
    (legacy / "config.json").write_text('{"test": true}')
    (legacy / "preferences.json").write_text("{}")

    # Setup canonical directory
    canonical = tmp_path / ".config" / "file-organizer"
    canonical.mkdir(parents=True)

    migrator = PathMigrator(legacy, canonical)
    migrator.migrate()

    # Verify files copied
    assert (canonical / "config.json").exists()
    assert (canonical / "config.json").read_text() == '{"test": true}'
    assert (canonical / "preferences.json").exists()


def test_path_migrator_creates_backup(tmp_path):
    """Should create backup of legacy path before migration"""
    legacy = tmp_path / ".file-organizer"
    legacy.mkdir()
    (legacy / "config.json").write_text('{"original": true}')

    canonical = tmp_path / ".config" / "file-organizer"
    canonical.mkdir(parents=True)

    migrator = PathMigrator(legacy, canonical)
    backup = migrator.backup_legacy_path()

    assert backup.exists()
    assert (backup / "config.json").exists()


def test_path_migrator_logs_migration(tmp_path):
    """Should log migration details for audit trail"""
    legacy = tmp_path / ".file-organizer"
    legacy.mkdir()

    canonical = tmp_path / ".config" / "file-organizer"
    canonical.mkdir(parents=True)

    migrator = PathMigrator(legacy, canonical)
    log_entry = migrator.create_migration_log()

    assert log_entry["from"] == str(legacy)
    assert log_entry["to"] == str(canonical)
    assert "timestamp" in log_entry
    assert "status" in log_entry
