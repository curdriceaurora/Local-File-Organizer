"""Traversal-safety regression tests for the batch 1 ``safe_walk`` migration (#1671).

Covers the call sites in ``config/`` and ``methodologies/`` that previously
walked user-supplied roots with a raw ``rglob("*")``:

- ``config/path_migration.PathMigrator.migrate``
- ``methodologies/johnny_decimal/system.JohnnyDecimalSystem.initialize_from_directory``
- ``methodologies/para/ai/file_mover.PARAFileMover.bulk_organize``
- ``methodologies/para/ai/file_mover.PARAFileMover.suggest_archive``

Each site is asserted on two axes: a symlink whose target lives outside the
walked root must never be reached, and dot-prefixed entries are included only
where that site deliberately wants them.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.config.path_migration import PathMigrator
from file_organizer.methodologies.johnny_decimal.system import JohnnyDecimalSystem
from file_organizer.methodologies.para.ai.file_mover import PARAFileMover
from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig

pytestmark = [
    pytest.mark.security,
    pytest.mark.unit,
    pytest.mark.integration,
    pytest.mark.ci,
]

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink hardening is POSIX-focused"
)


def _mover(tmp_path: Path, *, confidence: float = 0.9) -> PARAFileMover:
    """A PARAFileMover whose engine always returns a usable suggestion."""
    suggestion = MagicMock()
    suggestion.category = PARACategory.PROJECT
    suggestion.confidence = confidence
    suggestion.reasoning = ["test"]
    suggestion.suggested_subfolder = None

    engine = MagicMock()
    engine.suggest.return_value = suggestion
    return PARAFileMover(PARAConfig(), suggestion_engine=engine, root_dir=tmp_path)


class TestPathMigratorTraversal:
    """PathMigrator.migrate copies config, but must not chase links out of it."""

    @posix_only
    def test_migrate_does_not_copy_through_symlink_escaping_legacy_root(
        self, tmp_path: Path
    ) -> None:
        """A symlink in the legacy dir pointing outside it is not migrated."""
        secret = tmp_path / "secret.txt"
        secret.write_text("sensitive data outside the config tree")

        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "settings.json").write_text("{}")
        (legacy / "escape.txt").symlink_to(secret)

        canonical = tmp_path / "canonical"

        PathMigrator(legacy, canonical).migrate()

        assert (canonical / "settings.json").exists(), "real config file must migrate"
        assert not (canonical / "escape.txt").exists(), (
            "symlink escaping the legacy root must not be migrated"
        )

    @posix_only
    def test_backup_preserves_symlink_instead_of_dereferencing_it(self, tmp_path: Path) -> None:
        """The pre-migration backup must not materialise the link's target.

        ``backup_legacy_path()`` runs before the hardened ``migrate()`` loop and
        uses ``shutil.copytree``, which follows symlinks unless told otherwise.
        Without ``symlinks=True`` the escaping link's *contents* land inside the
        backup — the same data escape ``safe_walk`` prevents in ``migrate()``,
        one directory over.
        """
        secret = tmp_path / "secret.txt"
        secret.write_text("sensitive data outside the config tree")

        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "settings.json").write_text("{}")
        (legacy / "escape.txt").symlink_to(secret)

        migrator = PathMigrator(legacy, tmp_path / "canonical")
        migrator.migrate()

        assert migrator.backup_path is not None
        backed_up_link = migrator.backup_path / "escape.txt"

        assert backed_up_link.is_symlink(), "the backup must keep the link as a link"
        assert backed_up_link.readlink() == secret, "the link must still point at the original"

        # Decisive: no *regular file* anywhere in the backup carries the external
        # content. A dereferencing copytree would have written it as one.
        materialised = [
            p
            for p in migrator.backup_path.rglob("*")
            if p.is_file()
            and not p.is_symlink()
            and "sensitive data" in p.read_text(errors="ignore")
        ]
        assert materialised == [], (
            f"backup dereferenced the escaping link into real files: {materialised}"
        )

    def test_migrate_copies_hidden_config_files(self, tmp_path: Path) -> None:
        """Dotfiles are real config and must survive migration.

        Characterization guard: this site deliberately opts into hidden entries
        because dropping them silently loses user configuration.
        """
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / ".env").write_text("TOKEN=abc")
        (legacy / "nested").mkdir()
        (legacy / "nested" / ".hidden_prefs").write_text("theme=dark")

        canonical = tmp_path / "canonical"

        PathMigrator(legacy, canonical).migrate()

        assert (canonical / ".env").read_text() == "TOKEN=abc"
        assert (canonical / "nested" / ".hidden_prefs").exists()


class TestJohnnyDecimalInitTraversal:
    """initialize_from_directory scans names for numbers — not through links."""

    def test_initialize_skips_hidden_directories(self, tmp_path: Path) -> None:
        """A dot-prefixed directory is not registered even if it looks numbered."""
        (tmp_path / "10 Finance").mkdir()
        (tmp_path / ".20 Hidden").mkdir()

        system = JohnnyDecimalSystem()
        system.initialize_from_directory(tmp_path)

        registered = set(system.generator._used_numbers)
        assert "10" in registered
        assert "20" not in registered, "hidden directory must not register a number"

    @posix_only
    def test_initialize_does_not_register_symlinked_entries(self, tmp_path: Path) -> None:
        """A symlink named like a JD entry is not registered."""
        outside = tmp_path / "outside"
        outside.mkdir()

        root = tmp_path / "root"
        root.mkdir()
        (root / "10 Finance").mkdir()
        (root / "20 Escape").symlink_to(outside, target_is_directory=True)

        system = JohnnyDecimalSystem()
        system.initialize_from_directory(root)

        registered = set(system.generator._used_numbers)
        assert "10" in registered
        assert "20" not in registered, "symlinked entry must not register a number"


class TestBulkOrganizeTraversal:
    """bulk_organize moves files — it must not pick up links or dotfiles."""

    @posix_only
    def test_bulk_organize_skips_symlinked_files(self, tmp_path: Path) -> None:
        """A symlink to a file outside the scanned directory is not organized."""
        secret = tmp_path / "secret.txt"
        secret.write_text("outside")

        src = tmp_path / "src"
        src.mkdir()
        (src / "real.txt").write_text("inside")
        (src / "link.txt").symlink_to(secret)

        report = _mover(tmp_path).bulk_organize(src, dry_run=True)

        assert report.total_files == 1, "only the real file should be collected"

    def test_bulk_organize_skips_hidden_files(self, tmp_path: Path) -> None:
        """Dotfiles are not relocated by a bulk organize run."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "real.txt").write_text("inside")
        (src / ".gitignore").write_text("*.pyc")

        report = _mover(tmp_path).bulk_organize(src, dry_run=True)

        assert report.total_files == 1, "hidden file must not be organized"


def _backdate(path: Path, days: int = 400) -> None:
    """Age a file so suggest_archive considers it inactive."""
    old = time.time() - days * 86400
    os.utime(path, (old, old))


class TestSuggestArchiveTraversal:
    """suggest_archive proposes moves — same exclusions as bulk_organize."""

    @posix_only
    def test_suggest_archive_skips_symlinked_files(self, tmp_path: Path) -> None:
        """A symlink is never proposed for archiving."""
        secret = tmp_path / "secret.txt"
        secret.write_text("outside")
        _backdate(secret)

        src = tmp_path / "src"
        src.mkdir()
        (src / "link.txt").symlink_to(secret)

        suggestions = _mover(tmp_path).suggest_archive(src, inactive_days=180)

        assert suggestions == [], "symlink must not be proposed for archiving"

    def test_suggest_archive_skips_hidden_files(self, tmp_path: Path) -> None:
        """Dotfiles are never proposed for archiving."""
        src = tmp_path / "src"
        src.mkdir()
        hidden = src / ".gitignore"
        hidden.write_text("*.pyc")
        _backdate(hidden)

        suggestions = _mover(tmp_path).suggest_archive(src, inactive_days=180)

        assert suggestions == [], "hidden file must not be proposed for archiving"

    def test_suggest_archive_still_proposes_real_inactive_files(self, tmp_path: Path) -> None:
        """Characterization guard: ordinary inactive files are still proposed."""
        src = tmp_path / "src"
        src.mkdir()
        stale = src / "old_report.txt"
        stale.write_text("stale")
        _backdate(stale)

        suggestions = _mover(tmp_path).suggest_archive(src, inactive_days=180)

        assert [s.file_path for s in suggestions] == [stale]
