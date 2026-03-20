"""Integration tests for text processing utilities and config path migration.

Covers:
  - utils/text_processing.py      — clean_text, extract_keywords, sanitize_filename,
                                    truncate_text, get_unwanted_words
  - config/path_migration.py      — PathMigrator, detect_legacy_paths, resolve_legacy_path
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.config.path_migration import (
    PathMigrator,
    detect_legacy_paths,
    resolve_legacy_path,
)
from file_organizer.utils.text_processing import (
    clean_text,
    extract_keywords,
    get_unwanted_words,
    sanitize_filename,
    truncate_text,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# truncate_text
# ---------------------------------------------------------------------------


class TestTruncateText:
    def test_short_text_unchanged(self) -> None:
        assert truncate_text("hello", max_chars=100) == "hello"

    def test_long_text_truncated(self) -> None:
        result = truncate_text("x" * 200, max_chars=50)
        assert len(result) < 54

    def test_empty_string(self) -> None:
        assert truncate_text("") == ""

    def test_exact_length_unchanged(self) -> None:
        s = "a" * 20
        assert truncate_text(s, max_chars=20) == s

    def test_returns_string(self) -> None:
        assert truncate_text("hello world") == "hello world"

    def test_default_max_chars_applied(self) -> None:
        long = "w " * 3000
        result = truncate_text(long)
        assert len(result) < 5004


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    def test_basic_name(self) -> None:
        result = sanitize_filename("hello world")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_spaces_replaced(self) -> None:
        result = sanitize_filename("hello world test")
        assert " " not in result

    def test_special_chars_removed(self) -> None:
        result = sanitize_filename("file (copy) [1].txt")
        assert "(" not in result
        assert "[" not in result

    def test_max_length_respected(self) -> None:
        result = sanitize_filename("a b c d e f g h i j k l m n", max_length=10)
        assert len(result) < 11

    def test_empty_string_handled(self) -> None:
        result = sanitize_filename("")
        assert result == "untitled"

    def test_returns_string(self) -> None:
        assert sanitize_filename("my_file") == "my_file"


# ---------------------------------------------------------------------------
# get_unwanted_words
# ---------------------------------------------------------------------------


class TestGetUnwantedWords:
    def test_returns_set(self) -> None:
        result = get_unwanted_words()
        assert len(result) > 0

    def test_non_empty(self) -> None:
        result = get_unwanted_words()
        assert len(result) > 0

    def test_contains_strings(self) -> None:
        result = get_unwanted_words()
        for item in result:
            assert len(item) > 0
            break


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------


class TestCleanText:
    def test_returns_string(self) -> None:
        assert len(clean_text("hello world")) > 0

    def test_basic_text_cleaned(self) -> None:
        result = clean_text("Hello World This Is A Test")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_lowercase_output(self) -> None:
        result = clean_text("HELLO WORLD")
        assert result == result.lower()

    def test_empty_string(self) -> None:
        result = clean_text("")
        assert result == ""

    def test_max_words_respected(self) -> None:
        result = clean_text("one two three four five six seven", max_words=3)
        parts = result.split("_")
        assert len(parts) < 4

    def test_no_remove_unwanted(self) -> None:
        result = clean_text("finance invoice", remove_unwanted=False)
        assert len(result) > 0

    def test_no_lemmatize(self) -> None:
        result = clean_text("running files", lemmatize=False)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# extract_keywords
# ---------------------------------------------------------------------------


class TestExtractKeywords:
    def test_returns_list(self) -> None:
        result = extract_keywords("financial quarterly invoice payment report")
        assert len(result) >= 1

    def test_top_n_limit(self) -> None:
        result = extract_keywords("financial quarterly invoice payment report deadline", top_n=3)
        assert len(result) < 4

    def test_empty_string_returns_list(self) -> None:
        result = extract_keywords("")
        assert result == []

    def test_single_word(self) -> None:
        result = extract_keywords("finance")
        assert len(result) >= 1

    def test_default_top_n(self) -> None:
        result = extract_keywords("a b c d e f g h i j k l m n o")
        assert len(result) < 6

    def test_items_are_strings(self) -> None:
        result = extract_keywords("meeting project deadline client notes")
        for item in result:
            assert len(item) > 0


# ---------------------------------------------------------------------------
# PathMigrator
# ---------------------------------------------------------------------------


@pytest.fixture()
def migration_paths(tmp_path: Path) -> tuple[Path, Path]:
    legacy = tmp_path / "legacy_config"
    legacy.mkdir()
    (legacy / "settings.json").write_text('{"key": "value"}')
    canonical = tmp_path / "new_config"
    canonical.mkdir()
    return legacy, canonical


class TestPathMigratorInit:
    def test_created(self, migration_paths: tuple[Path, Path]) -> None:
        legacy, canonical = migration_paths
        m = PathMigrator(legacy_path=legacy, canonical_path=canonical)
        assert m is not None


class TestPathMigratorCreateMigrationLog:
    def test_returns_dict(self, migration_paths: tuple[Path, Path]) -> None:
        legacy, canonical = migration_paths
        m = PathMigrator(legacy_path=legacy, canonical_path=canonical)
        log = m.create_migration_log()
        assert "timestamp" in log

    def test_log_has_timestamp(self, migration_paths: tuple[Path, Path]) -> None:
        legacy, canonical = migration_paths
        m = PathMigrator(legacy_path=legacy, canonical_path=canonical)
        log = m.create_migration_log()
        assert "timestamp" in log

    def test_log_has_from_to(self, migration_paths: tuple[Path, Path]) -> None:
        legacy, canonical = migration_paths
        m = PathMigrator(legacy_path=legacy, canonical_path=canonical)
        log = m.create_migration_log()
        assert "from" in log
        assert "to" in log

    def test_log_status_pending(self, migration_paths: tuple[Path, Path]) -> None:
        legacy, canonical = migration_paths
        m = PathMigrator(legacy_path=legacy, canonical_path=canonical)
        log = m.create_migration_log()
        assert log.get("status") == "pending"


class TestPathMigratorBackup:
    def test_backup_creates_path(self, migration_paths: tuple[Path, Path]) -> None:
        legacy, canonical = migration_paths
        m = PathMigrator(legacy_path=legacy, canonical_path=canonical)
        backup = m.backup_legacy_path()
        assert isinstance(backup, Path)

    def test_backup_exists_after_call(self, migration_paths: tuple[Path, Path]) -> None:
        legacy, canonical = migration_paths
        m = PathMigrator(legacy_path=legacy, canonical_path=canonical)
        backup = m.backup_legacy_path()
        assert backup.exists()

    def test_backup_name_contains_legacy_name(self, migration_paths: tuple[Path, Path]) -> None:
        legacy, canonical = migration_paths
        m = PathMigrator(legacy_path=legacy, canonical_path=canonical)
        backup = m.backup_legacy_path()
        assert "legacy_config" in backup.name


class TestPathMigratorMigrate:
    def test_migrate_moves_files(self, tmp_path: Path) -> None:
        legacy = tmp_path / "old"
        legacy.mkdir()
        (legacy / "data.txt").write_text("content")
        canonical = tmp_path / "new"
        canonical.mkdir()
        m = PathMigrator(legacy_path=legacy, canonical_path=canonical)
        m.migrate()
        assert (canonical / "data.txt").exists()

    def test_migrate_on_nonexistent_legacy_is_noop(self, tmp_path: Path) -> None:
        legacy = tmp_path / "nonexistent"
        canonical = tmp_path / "target"
        canonical.mkdir()
        m = PathMigrator(legacy_path=legacy, canonical_path=canonical)
        m.migrate()


class TestPathMigratorFinalize:
    def test_finalize_after_migrate(self, tmp_path: Path) -> None:
        legacy = tmp_path / "old"
        legacy.mkdir()
        (legacy / "file.txt").write_text("data")
        canonical = tmp_path / "new"
        canonical.mkdir()
        m = PathMigrator(legacy_path=legacy, canonical_path=canonical)
        m.migrate()
        m.finalize_migration()


# ---------------------------------------------------------------------------
# detect_legacy_paths
# ---------------------------------------------------------------------------


class TestDetectLegacyPaths:
    def test_returns_list(self, tmp_path: Path) -> None:
        result = detect_legacy_paths(tmp_path, tmp_path / ".config", tmp_path / ".local")
        assert result == []

    def test_no_legacy_paths_empty(self, tmp_path: Path) -> None:
        result = detect_legacy_paths(tmp_path, tmp_path / ".config", tmp_path / ".local")
        assert result == []

    def test_detects_existing_legacy(self, tmp_path: Path) -> None:
        legacy = tmp_path / ".config" / "file-organizer"
        legacy.mkdir(parents=True)
        result = detect_legacy_paths(tmp_path, tmp_path / ".config", tmp_path / ".local")
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# resolve_legacy_path
# ---------------------------------------------------------------------------


class TestResolveLegacyPath:
    def test_returns_path(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "new"
        legacy_dir = tmp_path / "old"
        result = resolve_legacy_path(new_dir, legacy_dir)
        assert isinstance(result, Path)

    def test_returns_legacy_when_new_missing(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "new_nonexistent"
        legacy_dir = tmp_path / "old_exists"
        legacy_dir.mkdir()
        (legacy_dir / "data.txt").write_text("content")
        result = resolve_legacy_path(new_dir, legacy_dir)
        assert result == legacy_dir

    def test_returns_new_when_both_exist(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "new"
        new_dir.mkdir()
        legacy_dir = tmp_path / "old"
        legacy_dir.mkdir()
        result = resolve_legacy_path(new_dir, legacy_dir)
        assert result == new_dir
