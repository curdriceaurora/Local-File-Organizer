"""End-to-end integration tests for the ``fo dedupe`` CLI command.

These drive :func:`dedupe_command` against real directories full of real
duplicate files, exercising the whole pipeline — hashing, grouping,
strategy selection, backup, and deletion — with no service mocking. Only
non-interactive strategies in ``--batch`` mode are used so the runs stay
deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.cli.dedupe import dedupe_command

pytestmark = [pytest.mark.integration, pytest.mark.ci]

# Safe mode writes removed copies here (inside the scanned workspace), so
# assertions on the user's own files must exclude this directory.
BACKUP_DIR_NAME = ".file_organizer_backups"


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _workspace_files(root: Path) -> list[Path]:
    """All real files under *root*, excluding the safe-mode backup dir."""
    return [p for p in root.rglob("*") if p.is_file() and BACKUP_DIR_NAME not in p.parts]


@pytest.fixture
def dup_workspace(tmp_path: Path) -> Path:
    """A workspace with one duplicate group (3 copies) plus a unique file."""
    root = tmp_path / "ws"
    _write(root / "a.txt", "identical payload")
    _write(root / "nested/b.txt", "identical payload")
    _write(root / "nested/deep/c.txt", "identical payload")
    _write(root / "unique.txt", "one of a kind")
    return root


def test_batch_removal_deletes_duplicates_and_backs_up(dup_workspace: Path) -> None:
    """Batch removal deletes extra copies, keeps one, and writes backups."""
    exit_code = dedupe_command([str(dup_workspace), "--strategy", "oldest", "--batch"])
    assert exit_code == 0

    remaining = [p for p in _workspace_files(dup_workspace) if p.suffix == ".txt"]
    contents = [p.read_text(encoding="utf-8") for p in remaining]
    # One copy of the duplicate payload survives; the unique file is untouched.
    assert contents.count("identical payload") == 1
    assert "one of a kind" in contents

    # safe_mode is on by default: the two removed copies were backed up under
    # the workspace backup directory before deletion.
    backup_dir = dup_workspace / BACKUP_DIR_NAME
    assert backup_dir.is_dir()
    backed_up = [p for p in backup_dir.rglob("*") if p.is_file() and p.name != "manifest.json"]
    assert len(backed_up) == 2


def test_dry_run_preserves_all_files(
    dup_workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dry run reports duplicates without deleting anything."""
    before = sorted(p.name for p in _workspace_files(dup_workspace))
    exit_code = dedupe_command([str(dup_workspace), "--strategy", "newest", "--batch", "--dry-run"])
    assert exit_code == 0
    assert sorted(p.name for p in _workspace_files(dup_workspace)) == before

    # The run must actually have detected the duplicate group, not merely
    # left the tree untouched because nothing was found.
    out = capsys.readouterr().out
    assert "No duplicate files found" not in out


def test_no_safe_mode_deletes_without_backup(dup_workspace: Path) -> None:
    """With --no-safe-mode the duplicates are deleted and no backup is made."""
    exit_code = dedupe_command(
        [str(dup_workspace), "--strategy", "largest", "--batch", "--no-safe-mode"]
    )
    assert exit_code == 0

    payloads = [
        p.read_text(encoding="utf-8") for p in _workspace_files(dup_workspace) if p.suffix == ".txt"
    ]
    assert payloads.count("identical payload") == 1

    assert not (dup_workspace / BACKUP_DIR_NAME).exists(), (
        "no backup directory should exist with --no-safe-mode"
    )


def test_min_size_filter_skips_small_duplicates(dup_workspace: Path) -> None:
    """A min-size larger than the files leaves every duplicate in place."""
    before = sorted(p.name for p in _workspace_files(dup_workspace))
    exit_code = dedupe_command(
        [
            str(dup_workspace),
            "--strategy",
            "oldest",
            "--batch",
            "--min-size",
            "10000000",
        ]
    )
    assert exit_code == 0
    assert sorted(p.name for p in _workspace_files(dup_workspace)) == before


def test_no_duplicates_returns_success(tmp_path: Path) -> None:
    """A directory with only unique files exits 0 and deletes nothing."""
    root = tmp_path / "unique"
    _write(root / "one.txt", "alpha")
    _write(root / "two.txt", "beta")
    _write(root / "three.txt", "gamma")

    exit_code = dedupe_command([str(root), "--strategy", "oldest", "--batch", "--no-safe-mode"])
    assert exit_code == 0
    assert len(_workspace_files(root)) == 3


def test_missing_directory_returns_error() -> None:
    """A non-existent directory yields a non-zero exit code."""
    assert dedupe_command(["/no/such/directory/anywhere"]) == 1


def test_path_that_is_a_file_returns_error(tmp_path: Path) -> None:
    """Passing a file instead of a directory yields a non-zero exit code."""
    target = _write(tmp_path / "just_a_file.txt", "data")
    assert dedupe_command([str(target)]) == 1


def test_md5_algorithm_non_recursive(tmp_path: Path) -> None:
    """Non-recursive md5 scan only dedupes top-level duplicates."""
    root = tmp_path / "ws"
    _write(root / "top1.txt", "same top")
    _write(root / "top2.txt", "same top")
    _write(root / "sub/nested.txt", "same top")  # ignored: non-recursive

    exit_code = dedupe_command(
        [
            str(root),
            "--algorithm",
            "md5",
            "--strategy",
            "oldest",
            "--batch",
            "--no-recursive",
            "--no-safe-mode",
        ]
    )
    assert exit_code == 0

    # One of the two top-level copies is removed; the nested file is untouched.
    assert (root / "sub/nested.txt").exists()
    top_level = [p for p in root.glob("*.txt") if p.is_file()]
    assert len(top_level) == 1
