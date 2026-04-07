# tests/integration/test_dedupe_removal_integration.py
"""Integration tests for file_organizer.cli.dedupe_removal.

Tests remove_files() with real filesystem operations (create/delete via
tmp_path) and process_duplicate_group() with get_user_selection patched
to avoid interactive stdin.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from file_organizer.cli.dedupe_removal import process_duplicate_group, remove_files

pytestmark = [pytest.mark.integration, pytest.mark.ci]


@pytest.fixture()
def console() -> Console:
    return Console(quiet=True)


def _make_files(tmp_path: Path, count: int = 3, size: int = 50) -> list[dict]:
    """Create real temp files and return file-metadata dicts."""
    results = []
    for i in range(count):
        p = tmp_path / f"file_{i}.txt"
        p.write_bytes(b"x" * size)
        results.append({"path": p, "size": size, "mtime": 0.0})
    return results


class TestRemoveFiles:
    def test_deletes_specified_files(self, tmp_path: Path, console: Console) -> None:
        files = _make_files(tmp_path, count=3, size=50)
        removed, saved = remove_files(files, [0, 2], None, dry_run=False, console=console)

        assert removed == 2
        assert saved == 100  # 2 x 50 bytes
        assert not files[0]["path"].exists()
        assert files[1]["path"].exists()  # index 1 was not removed
        assert not files[2]["path"].exists()

    def test_dry_run_does_not_delete(self, tmp_path: Path, console: Console) -> None:
        files = _make_files(tmp_path, count=2, size=20)
        removed, saved = remove_files(files, [0, 1], None, dry_run=True, console=console)

        assert removed == 2
        assert saved == 40
        assert files[0]["path"].exists()  # dry run: file still present
        assert files[1]["path"].exists()

    def test_empty_indices_removes_nothing(self, tmp_path: Path, console: Console) -> None:
        files = _make_files(tmp_path, count=2)
        removed, saved = remove_files(files, [], None, dry_run=False, console=console)

        assert removed == 0
        assert saved == 0
        assert files[0]["path"].exists()
        assert files[1]["path"].exists()

    def test_oserror_on_missing_file_is_handled(self, tmp_path: Path, console: Console) -> None:
        files = _make_files(tmp_path, count=1, size=30)
        files[0]["path"].unlink()  # delete before calling remove_files

        removed, saved = remove_files(files, [0], None, dry_run=False, console=console)

        # OSError handled — zero files removed, no exception raised
        assert removed == 0
        assert saved == 0

    def test_with_backup_manager(self, tmp_path: Path, console: Console) -> None:
        files = _make_files(tmp_path, count=1, size=10)
        backup_manager = MagicMock()
        backup_manager.create_backup.return_value = tmp_path / "backup" / "file_0.txt"

        removed, saved = remove_files(files, [0], backup_manager, dry_run=False, console=console)

        assert removed == 1
        assert saved == 10  # one file of size 10 bytes
        assert not files[0]["path"].exists()  # original removed after backup
        backup_manager.create_backup.assert_called_once_with(files[0]["path"])


class TestProcessDuplicateGroup:
    def _make_group(self, tmp_path: Path, count: int = 2) -> MagicMock:
        """Build a MagicMock DuplicateGroup whose .files look like FileMetadata."""
        group = MagicMock()
        file_metas = []
        for i in range(count):
            p = tmp_path / f"dup_{i}.txt"
            p.write_bytes(b"dup" * 10)
            fm = MagicMock()
            fm.path = p
            fm.size = 30
            fm.modified_time.timestamp.return_value = float(i)
            file_metas.append(fm)
        group.files = file_metas
        return group

    def test_removes_file_when_user_selects_index(self, tmp_path: Path, console: Console) -> None:
        group = self._make_group(tmp_path, count=2)

        # Patch the source modules — the imports in dedupe_removal are lazy
        # (inside the function body) and never bind into the module namespace,
        # so we must patch where the names are defined.
        with (
            patch("file_organizer.cli.dedupe_display.display_duplicate_group"),
            patch(
                "file_organizer.cli.dedupe_strategy.select_files_to_keep",
                side_effect=lambda f, _s: f,
            ),
            patch("file_organizer.cli.dedupe_strategy.get_user_selection", return_value=[1]),
        ):
            removed, saved = process_duplicate_group(
                group_id=1,
                file_hash="abc123",
                group=group,
                total_groups=1,
                strategy="oldest",
                batch=True,
                backup_manager=None,
                dry_run=False,
                console=console,
            )

        assert removed == 1
        assert saved == 30

    def test_skip_when_user_selects_nothing(self, tmp_path: Path, console: Console) -> None:
        group = self._make_group(tmp_path, count=2)

        with (
            patch("file_organizer.cli.dedupe_display.display_duplicate_group"),
            patch(
                "file_organizer.cli.dedupe_strategy.select_files_to_keep",
                side_effect=lambda f, _s: f,
            ),
            patch("file_organizer.cli.dedupe_strategy.get_user_selection", return_value=[]),
        ):
            removed, saved = process_duplicate_group(
                group_id=1,
                file_hash="abc123",
                group=group,
                total_groups=1,
                strategy="oldest",
                batch=True,
                backup_manager=None,
                dry_run=False,
                console=console,
            )

        assert removed == 0
        assert saved == 0
