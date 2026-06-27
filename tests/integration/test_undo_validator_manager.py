"""Integration tests for undo/validator.py and undo/undo_manager.py.

Covers uncovered branches in:
  - undo/validator.py  — OperationValidator.validate_undo (all OperationType
                         branches, ROLLED_BACK / FAILED status, hash mismatch,
                         path-occupied, parent-missing),
                         validate_redo, check_file_integrity, check_conflicts
  - undo/undo_manager.py — undo_last_operation (empty history, id=None),
                           undo_operation (not found, already rolled back,
                           validation failure, warnings path),
                           redo_last_operation, redo_operation,
                           can_undo, can_redo
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.history.models import Operation, OperationStatus, OperationType
from file_organizer.undo.models import ConflictType, ValidationResult
from file_organizer.undo.validator import OperationValidator

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_op(
    tmp_path: Path,
    op_type: OperationType = OperationType.MOVE,
    status: OperationStatus = OperationStatus.COMPLETED,
    source_name: str = "src.txt",
    dest_name: str | None = "dst.txt",
    file_hash: str | None = None,
    op_id: int | None = 1,
) -> Operation:
    src = tmp_path / source_name
    dest = (tmp_path / dest_name) if dest_name else None
    return Operation(
        id=op_id,
        operation_type=op_type,
        timestamp=datetime.now(UTC),
        source_path=src,
        destination_path=dest,
        status=status,
        file_hash=file_hash,
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# OperationValidator — validate_undo status branches
# ---------------------------------------------------------------------------


class TestValidateUndoStatusBranches:
    def test_rolled_back_returns_cannot_proceed(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_op(tmp_path, status=OperationStatus.ROLLED_BACK)
        result = v.validate_undo(op)
        assert not result.can_proceed
        assert "rolled back" in (result.error_message or "").lower()

    def test_failed_status_adds_warning(self, tmp_path: Path) -> None:
        # FAILED status doesn't block but adds a warning
        v = OperationValidator(trash_dir=tmp_path / "trash")
        # make dest exist so move validation passes
        dest = tmp_path / "dst.txt"
        dest.write_text("content")
        src = tmp_path / "src.txt"  # source available (doesn't exist)
        op = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.FAILED,
        )
        result = v.validate_undo(op)
        assert len(result.warnings) > 0
        assert "failed" in result.warnings[0].lower()


# ---------------------------------------------------------------------------
# OperationValidator — validate_undo MOVE branches
# ---------------------------------------------------------------------------


class TestValidateUndoMove:
    def test_clean_move_no_conflicts(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        dest = tmp_path / "dst.txt"
        dest.write_text("hello")
        # source must NOT exist (available)
        src = tmp_path / "subdir" / "src.txt"
        src.parent.mkdir()
        op = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert result.can_proceed
        assert len(result.conflicts) == 0

    def test_destination_missing_adds_file_missing_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        # dest does NOT exist
        src = tmp_path / "src.txt"
        dest = tmp_path / "ghost.txt"
        op = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed
        conflict_types = [c.conflict_type for c in result.conflicts]
        assert any("missing" in str(ct).lower() for ct in conflict_types)

    def test_hash_mismatch_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        dest = tmp_path / "dst.txt"
        dest.write_text("content")
        src = tmp_path / "newdir" / "src.txt"
        src.parent.mkdir()
        op = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
            file_hash="a" * 64,  # intentionally wrong hash
        )
        result = v.validate_undo(op)
        assert not result.can_proceed
        assert any("hash" in str(c.conflict_type).lower() for c in result.conflicts)

    def test_source_occupied_adds_path_occupied_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        dest = tmp_path / "dst.txt"
        dest.write_text("hello")
        # src already exists → occupied
        src = tmp_path / "src.txt"
        src.write_text("blocker")
        op = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed
        assert any("occupied" in str(c.conflict_type).lower() for c in result.conflicts)

    def test_parent_directory_missing_adds_parent_missing_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        dest = tmp_path / "dst.txt"
        dest.write_text("hello")
        # source parent does NOT exist
        src = tmp_path / "nonexistent_parent" / "src.txt"
        op = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed
        assert any("parent" in str(c.conflict_type).lower() for c in result.conflicts)

    def test_none_destination_path_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "src.txt"
        op = Operation(
            id=1,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=None,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        # destination_path is None → FILE_MISSING conflict
        assert not result.can_proceed


# ---------------------------------------------------------------------------
# OperationValidator — validate_undo RENAME branches
# ---------------------------------------------------------------------------


class TestValidateUndoRename:
    def test_clean_rename_no_conflicts(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        dest = tmp_path / "newname.txt"
        dest.write_text("data")
        src = tmp_path / "oldname.txt"  # original name; available
        op = Operation(
            id=2,
            operation_type=OperationType.RENAME,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert result.can_proceed

    def test_rename_destination_missing(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        dest = tmp_path / "missing.txt"  # does not exist
        src = tmp_path / "orig.txt"
        op = Operation(
            id=2,
            operation_type=OperationType.RENAME,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed

    def test_rename_hash_mismatch(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        dest = tmp_path / "newname.txt"
        dest.write_text("modified content")
        src = tmp_path / "oldname.txt"
        op = Operation(
            id=2,
            operation_type=OperationType.RENAME,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
            file_hash="b" * 64,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed

    def test_rename_original_name_occupied(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        dest = tmp_path / "newname.txt"
        dest.write_text("data")
        src = tmp_path / "oldname.txt"
        src.write_text("blocker")  # original name already taken
        op = Operation(
            id=2,
            operation_type=OperationType.RENAME,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed


# ---------------------------------------------------------------------------
# OperationValidator — validate_undo DELETE branches
# ---------------------------------------------------------------------------


class TestValidateUndoDelete:
    def test_file_in_trash_no_conflicts(self, tmp_path: Path) -> None:
        trash = tmp_path / "trash"
        trash.mkdir()
        v = OperationValidator(trash_dir=trash)
        # Place the file in trash under operation_id subdirectory
        src = tmp_path / "deleted.txt"
        trash_subdir = trash / "1"
        trash_subdir.mkdir()
        (trash_subdir / "deleted.txt").write_text("content")
        op = Operation(
            id=1,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert result.can_proceed

    def test_file_not_in_trash_adds_conflict(self, tmp_path: Path) -> None:
        trash = tmp_path / "trash"
        trash.mkdir()
        v = OperationValidator(trash_dir=trash)
        src = tmp_path / "deleted.txt"
        op = Operation(
            id=99,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed
        assert any("missing" in str(c.conflict_type).lower() for c in result.conflicts)

    def test_delete_source_occupied_adds_conflict(self, tmp_path: Path) -> None:
        trash = tmp_path / "trash"
        trash.mkdir()
        v = OperationValidator(trash_dir=trash)
        src = tmp_path / "deleted.txt"
        # Place in trash
        trash_subdir = trash / "5"
        trash_subdir.mkdir()
        (trash_subdir / "deleted.txt").write_text("in trash")
        # But original location is now occupied
        src.write_text("something else")
        op = Operation(
            id=5,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed
        assert any("occupied" in str(c.conflict_type).lower() for c in result.conflicts)

    def test_delete_parent_missing_adds_conflict(self, tmp_path: Path) -> None:
        trash = tmp_path / "trash"
        trash.mkdir()
        v = OperationValidator(trash_dir=trash)
        src = tmp_path / "gone_parent" / "file.txt"
        trash_subdir = trash / "7"
        trash_subdir.mkdir()
        (trash_subdir / "file.txt").write_text("in trash")
        op = Operation(
            id=7,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        # parent gone_parent doesn't exist → PARENT_MISSING
        assert not result.can_proceed
        assert any("parent" in str(c.conflict_type).lower() for c in result.conflicts)


# ---------------------------------------------------------------------------
# OperationValidator — validate_undo COPY branches
# ---------------------------------------------------------------------------


class TestValidateUndoCopy:
    def test_copy_exists_no_conflicts(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        dest = tmp_path / "copy.txt"
        dest.write_text("copy content")
        src = tmp_path / "original.txt"
        op = Operation(
            id=3,
            operation_type=OperationType.COPY,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert result.can_proceed

    def test_copy_missing_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        dest = tmp_path / "missing_copy.txt"
        src = tmp_path / "original.txt"
        op = Operation(
            id=3,
            operation_type=OperationType.COPY,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed

    def test_copy_hash_mismatch_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        dest = tmp_path / "copy.txt"
        dest.write_text("modified")
        src = tmp_path / "original.txt"
        op = Operation(
            id=3,
            operation_type=OperationType.COPY,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
            file_hash="c" * 64,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed

    def test_copy_none_destination_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "original.txt"
        op = Operation(
            id=3,
            operation_type=OperationType.COPY,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=None,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed


# ---------------------------------------------------------------------------
# OperationValidator — validate_undo HARDLINK / SYMLINK branches
# ---------------------------------------------------------------------------


class TestValidateUndoLinks:
    def test_hardlink_matching_inode_can_proceed(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        source = tmp_path / "src.txt"
        link = tmp_path / "link.txt"
        source.write_text("data")
        os.link(source, link)

        op = Operation(
            id=21,
            operation_type=OperationType.HARDLINK,
            timestamp=datetime.now(UTC),
            source_path=source,
            destination_path=link,
            status=OperationStatus.COMPLETED,
        )

        result = v.validate_undo(op)

        assert result.can_proceed

    def test_hardlink_missing_destination_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        source = tmp_path / "src.txt"
        source.write_text("data")
        op = Operation(
            id=22,
            operation_type=OperationType.HARDLINK,
            timestamp=datetime.now(UTC),
            source_path=source,
            destination_path=tmp_path / "missing-link.txt",
            status=OperationStatus.COMPLETED,
        )

        result = v.validate_undo(op)

        assert not result.can_proceed
        assert any(c.description == "Hardlink has already been deleted" for c in result.conflicts)

    def test_hardlink_none_destination_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        source = tmp_path / "src.txt"
        source.write_text("data")
        op = Operation(
            id=34,
            operation_type=OperationType.HARDLINK,
            timestamp=datetime.now(UTC),
            source_path=source,
            destination_path=None,
            status=OperationStatus.COMPLETED,
        )

        result = v.validate_undo(op)

        assert not result.can_proceed
        assert any(c.description == "Hardlink has already been deleted" for c in result.conflicts)

    def test_hardlink_destination_exists_error_adds_permission_conflict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        source = tmp_path / "src.txt"
        link = tmp_path / "link.txt"
        source.write_text("data")
        os.link(source, link)
        op = Operation(
            id=35,
            operation_type=OperationType.HARDLINK,
            timestamp=datetime.now(UTC),
            source_path=source,
            destination_path=link,
            status=OperationStatus.COMPLETED,
        )

        def fail_exists(self: Path) -> bool:
            if self == link:
                raise OSError("exists failed")
            return original_exists(self)

        original_exists = Path.exists
        monkeypatch.setattr(Path, "exists", fail_exists)

        result = v.validate_undo(op)

        assert not result.can_proceed
        assert any(c.conflict_type == ConflictType.PERMISSION_DENIED for c in result.conflicts)

    def test_hardlink_rejects_symlink_destination(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        source = tmp_path / "src.txt"
        link = tmp_path / "link.txt"
        source.write_text("data")
        link.symlink_to(source)
        op = Operation(
            id=23,
            operation_type=OperationType.HARDLINK,
            timestamp=datetime.now(UTC),
            source_path=source,
            destination_path=link,
            status=OperationStatus.COMPLETED,
        )

        result = v.validate_undo(op)

        assert not result.can_proceed
        assert any(
            c.description == "Hardlink was replaced with a symlink" for c in result.conflicts
        )

    def test_hardlink_detects_missing_source(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        source = tmp_path / "src.txt"
        link = tmp_path / "link.txt"
        link.write_text("replacement")
        op = Operation(
            id=24,
            operation_type=OperationType.HARDLINK,
            timestamp=datetime.now(UTC),
            source_path=source,
            destination_path=link,
            status=OperationStatus.COMPLETED,
        )

        result = v.validate_undo(op)

        assert not result.can_proceed
        assert any(c.description == "Source file no longer exists" for c in result.conflicts)

    def test_hardlink_detects_replaced_file(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        source = tmp_path / "src.txt"
        link = tmp_path / "link.txt"
        source.write_text("data")
        link.write_text("different")
        op = Operation(
            id=25,
            operation_type=OperationType.HARDLINK,
            timestamp=datetime.now(UTC),
            source_path=source,
            destination_path=link,
            status=OperationStatus.COMPLETED,
        )

        result = v.validate_undo(op)

        assert not result.can_proceed
        assert any(
            c.description == "Hardlink was replaced with a different file" for c in result.conflicts
        )

    def test_symlink_matching_target_can_proceed(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        source = tmp_path / "src.txt"
        link = tmp_path / "link.txt"
        source.write_text("data")
        link.symlink_to(source)
        op = Operation(
            id=26,
            operation_type=OperationType.SYMLINK,
            timestamp=datetime.now(UTC),
            source_path=source,
            destination_path=link,
            status=OperationStatus.COMPLETED,
        )

        result = v.validate_undo(op)

        assert result.can_proceed

    def test_symlink_missing_destination_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        source = tmp_path / "src.txt"
        source.write_text("data")
        op = Operation(
            id=27,
            operation_type=OperationType.SYMLINK,
            timestamp=datetime.now(UTC),
            source_path=source,
            destination_path=tmp_path / "missing-link.txt",
            status=OperationStatus.COMPLETED,
        )

        result = v.validate_undo(op)

        assert not result.can_proceed
        assert any(
            c.description == "Symlink has already been deleted or replaced"
            for c in result.conflicts
        )

    def test_symlink_detects_replaced_target(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        source = tmp_path / "src.txt"
        other = tmp_path / "other.txt"
        link = tmp_path / "link.txt"
        source.write_text("data")
        other.write_text("other")
        link.symlink_to(other)
        op = Operation(
            id=28,
            operation_type=OperationType.SYMLINK,
            timestamp=datetime.now(UTC),
            source_path=source,
            destination_path=link,
            status=OperationStatus.COMPLETED,
        )

        result = v.validate_undo(op)

        assert not result.can_proceed
        assert any(
            c.description == "Symlink was replaced with a different target"
            for c in result.conflicts
        )


# ---------------------------------------------------------------------------
# OperationValidator — validate_undo CREATE branches
# ---------------------------------------------------------------------------


class TestValidateUndoCreate:
    def test_created_file_exists_no_conflicts(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "created.txt"
        src.write_text("exists")
        op = Operation(
            id=4,
            operation_type=OperationType.CREATE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert result.can_proceed

    def test_created_file_missing_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "vanished.txt"
        op = Operation(
            id=4,
            operation_type=OperationType.CREATE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.COMPLETED,
        )
        result = v.validate_undo(op)
        assert not result.can_proceed


# ---------------------------------------------------------------------------
# OperationValidator — unknown operation type branch
# ---------------------------------------------------------------------------


class TestValidateUndoUnknownType:
    def test_unknown_type_returns_cannot_proceed(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "src.txt"
        op = Operation(
            id=9,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.COMPLETED,
        )
        # Monkey-patch the operation_type to a value no branch handles
        op.operation_type = "unknown_type"  # type: ignore[assignment]
        result = v.validate_undo(op)
        assert not result.can_proceed
        assert "unknown" in (result.error_message or "").lower()


# ---------------------------------------------------------------------------
# OperationValidator — validate_redo branches
# ---------------------------------------------------------------------------


class TestValidateRedo:
    def test_not_rolled_back_returns_cannot_proceed(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_op(tmp_path, status=OperationStatus.COMPLETED)
        result = v.validate_redo(op)
        assert not result.can_proceed
        assert "rolled back" in (result.error_message or "").lower()

    def test_redo_move_source_exists_no_conflicts(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "src.txt"
        src.write_text("back here after undo")
        dest = tmp_path / "notexists" / "dst.txt"
        op = Operation(
            id=10,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.ROLLED_BACK,
        )
        result = v.validate_redo(op)
        assert result.can_proceed

    def test_redo_move_source_missing_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "ghost.txt"  # doesn't exist
        dest = tmp_path / "somedir" / "dst.txt"
        op = Operation(
            id=11,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.ROLLED_BACK,
        )
        result = v.validate_redo(op)
        assert not result.can_proceed

    def test_redo_move_destination_occupied_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "src.txt"
        src.write_text("exists")
        dest = tmp_path / "dst.txt"
        dest.write_text("already here")
        op = Operation(
            id=12,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.ROLLED_BACK,
        )
        result = v.validate_redo(op)
        assert not result.can_proceed

    def test_redo_delete_source_exists(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "to_delete.txt"
        src.write_text("exists")
        op = Operation(
            id=13,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.ROLLED_BACK,
        )
        result = v.validate_redo(op)
        assert result.can_proceed

    def test_redo_delete_source_missing_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "gone.txt"
        op = Operation(
            id=14,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.ROLLED_BACK,
        )
        result = v.validate_redo(op)
        assert not result.can_proceed

    def test_redo_copy_source_missing(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "missing_orig.txt"
        dest = tmp_path / "newcopy" / "dst.txt"
        op = Operation(
            id=15,
            operation_type=OperationType.COPY,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.ROLLED_BACK,
        )
        result = v.validate_redo(op)
        assert not result.can_proceed

    def test_redo_copy_destination_occupied(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "source.txt"
        src.write_text("source")
        dest = tmp_path / "occupied.txt"
        dest.write_text("already here")
        op = Operation(
            id=16,
            operation_type=OperationType.COPY,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.ROLLED_BACK,
        )
        result = v.validate_redo(op)
        assert not result.can_proceed

    def test_redo_hardlink_requires_destination(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "source.txt"
        src.write_text("source")
        op = Operation(
            id=29,
            operation_type=OperationType.HARDLINK,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=None,
            status=OperationStatus.ROLLED_BACK,
        )

        result = v.validate_redo(op)

        assert not result.can_proceed
        assert any(c.description == "Link destination was not recorded" for c in result.conflicts)

    def test_undo_hardlink_stat_error_adds_permission_conflict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "source.txt"
        dest = tmp_path / "link.txt"
        src.write_text("source")
        os.link(src, dest)
        op = Operation(
            id=32,
            operation_type=OperationType.HARDLINK,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )

        def fail_stat(self: Path, *args: object, **kwargs: object) -> os.stat_result:
            if self == src:
                raise PermissionError("stat denied")
            return original_stat(self, *args, **kwargs)

        original_stat = Path.stat
        monkeypatch.setattr(Path, "stat", fail_stat)

        result = v.validate_undo(op)

        assert not result.can_proceed
        assert any(c.conflict_type == ConflictType.PERMISSION_DENIED for c in result.conflicts)

    def test_undo_hardlink_destination_stat_error_adds_permission_conflict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "source.txt"
        dest = tmp_path / "link.txt"
        src.write_text("source")
        os.link(src, dest)
        op = Operation(
            id=36,
            operation_type=OperationType.HARDLINK,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )

        def fail_stat(self: Path, *args: object, **kwargs: object) -> os.stat_result:
            if self == dest:
                raise PermissionError("stat denied")
            return original_stat(self, *args, **kwargs)

        original_stat = Path.stat
        monkeypatch.setattr(Path, "stat", fail_stat)
        monkeypatch.setattr(Path, "exists", lambda self: True if self in {src, dest} else False)

        result = v.validate_undo(op)

        assert not result.can_proceed
        assert any(c.conflict_type == ConflictType.PERMISSION_DENIED for c in result.conflicts)

    def test_check_file_integrity_read_error_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        path = tmp_path / "file.txt"
        path.write_text("data")

        def fail_open(*args: object, **kwargs: object) -> object:
            raise OSError("read failed")

        monkeypatch.setattr("builtins.open", fail_open)

        assert v.check_file_integrity(path, "expected") is False

    def test_undo_symlink_resolve_loop_adds_permission_conflict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "source.txt"
        dest = tmp_path / "link.txt"
        src.write_text("source")
        dest.symlink_to(src)
        op = Operation(
            id=33,
            operation_type=OperationType.SYMLINK,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.COMPLETED,
        )

        def fail_resolve(self: Path, *args: object, **kwargs: object) -> Path:
            if self == dest:
                raise RuntimeError("Symlink loop from resolve")
            return original_resolve(self, *args, **kwargs)

        original_resolve = Path.resolve
        monkeypatch.setattr(Path, "resolve", fail_resolve)

        result = v.validate_undo(op)

        assert not result.can_proceed
        assert any(c.conflict_type == ConflictType.PERMISSION_DENIED for c in result.conflicts)

    def test_redo_symlink_destination_available_can_proceed(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "source.txt"
        dest = tmp_path / "link.txt"
        src.write_text("source")
        op = Operation(
            id=30,
            operation_type=OperationType.SYMLINK,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.ROLLED_BACK,
        )

        result = v.validate_redo(op)

        assert result.can_proceed

    def test_redo_symlink_destination_occupied_adds_conflict(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "source.txt"
        dest = tmp_path / "link.txt"
        src.write_text("source")
        dest.write_text("occupied")
        op = Operation(
            id=31,
            operation_type=OperationType.SYMLINK,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.ROLLED_BACK,
        )

        result = v.validate_redo(op)

        assert not result.can_proceed
        assert any("occupied" in str(c.conflict_type).lower() for c in result.conflicts)

    def test_redo_create_path_available(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "new_file.txt"  # doesn't exist → available
        op = Operation(
            id=17,
            operation_type=OperationType.CREATE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.ROLLED_BACK,
        )
        result = v.validate_redo(op)
        assert result.can_proceed

    def test_redo_create_path_occupied(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "existing.txt"
        src.write_text("occupied")
        op = Operation(
            id=18,
            operation_type=OperationType.CREATE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.ROLLED_BACK,
        )
        result = v.validate_redo(op)
        assert not result.can_proceed

    def test_redo_rename_delegates_to_redo_move(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "old.txt"
        src.write_text("exists")
        dest = tmp_path / "new.txt"  # available
        op = Operation(
            id=19,
            operation_type=OperationType.RENAME,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=dest,
            status=OperationStatus.ROLLED_BACK,
        )
        result = v.validate_redo(op)
        assert result.can_proceed

    def test_redo_unknown_type_cannot_proceed(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        src = tmp_path / "src.txt"
        op = Operation(
            id=20,
            operation_type=OperationType.MOVE,
            timestamp=datetime.now(UTC),
            source_path=src,
            status=OperationStatus.ROLLED_BACK,
        )
        op.operation_type = "unknown_type"  # type: ignore[assignment]
        result = v.validate_redo(op)
        assert not result.can_proceed


# ---------------------------------------------------------------------------
# OperationValidator — check_file_integrity
# ---------------------------------------------------------------------------


class TestCheckFileIntegrity:
    def test_correct_hash_returns_true(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        f = tmp_path / "file.txt"
        f.write_text("integrity check")
        actual = _sha256(f)
        assert v.check_file_integrity(f, actual) is True

    def test_wrong_hash_returns_false(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        f = tmp_path / "file.txt"
        f.write_text("content")
        assert v.check_file_integrity(f, "d" * 64) is False

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        assert v.check_file_integrity(tmp_path / "ghost.txt", "e" * 64) is False

    def test_directory_returns_false(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        # directories are not files → False
        assert v.check_file_integrity(tmp_path, "f" * 64) is False


# ---------------------------------------------------------------------------
# OperationValidator — check_conflicts (is_undo / is_redo branch)
# ---------------------------------------------------------------------------


class TestCheckConflicts:
    def test_undo_path_delegates_to_validate_undo(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_op(tmp_path, status=OperationStatus.ROLLED_BACK)
        conflicts = v.check_conflicts(op, is_undo=True)
        # ROLLED_BACK means undo fails — but check_conflicts returns [] because
        # validate_undo returns ValidationResult(can_proceed=False) with no conflicts list
        assert conflicts == []

    def test_redo_path_delegates_to_validate_redo(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        # COMPLETED status → validate_redo returns cannot proceed, no conflicts
        op = _make_op(tmp_path, status=OperationStatus.COMPLETED)
        conflicts = v.check_conflicts(op, is_undo=False)
        assert conflicts == []


# ---------------------------------------------------------------------------
# OperationValidator — _get_trash_path
# ---------------------------------------------------------------------------


class TestGetTrashPath:
    def test_get_trash_path_prefers_recorded_destination(self, tmp_path: Path) -> None:
        trash = tmp_path / "trash"
        v = OperationValidator(trash_dir=trash)
        src = tmp_path / "doc.txt"
        recorded = trash / "txn" / "doc.txt"
        recorded.parent.mkdir(parents=True)
        recorded.write_text("x")
        op = Operation(
            id=999,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=recorded,
            status=OperationStatus.COMPLETED,
        )

        assert v._get_trash_path(op) == recorded

    def test_get_trash_path_finds_operation_id_layout(self, tmp_path: Path) -> None:
        trash = tmp_path / "trash"
        v = OperationValidator(trash_dir=trash)
        src = tmp_path / "doc.txt"
        recovered = trash / "42" / "doc.txt"
        recovered.parent.mkdir(parents=True)
        recovered.write_text("x")
        op = Operation(
            id=42,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=None,
            status=OperationStatus.COMPLETED,
        )

        assert v._get_trash_path(op) == recovered

    def test_get_trash_path_falls_back_to_filename_search(self, tmp_path: Path) -> None:
        trash = tmp_path / "trash"
        v = OperationValidator(trash_dir=trash)
        src = tmp_path / "doc.txt"
        recovered = trash / "nested" / "doc.txt"
        recovered.parent.mkdir(parents=True)
        recovered.write_text("x")
        op = Operation(
            id=999,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(UTC),
            source_path=src,
            destination_path=None,
            status=OperationStatus.COMPLETED,
        )

        assert v._get_trash_path(op) == recovered

    def test_get_trash_path_returns_none_when_not_found(self, tmp_path: Path) -> None:
        v = OperationValidator(trash_dir=tmp_path / "trash")
        op = Operation(
            id=999,
            operation_type=OperationType.DELETE,
            timestamp=datetime.now(UTC),
            source_path=tmp_path / "doc.txt",
            destination_path=None,
            status=OperationStatus.COMPLETED,
        )

        assert v._get_trash_path(op) is None


# ---------------------------------------------------------------------------
# UndoManager — undo_last_operation
# ---------------------------------------------------------------------------


class TestUndoManagerUndoLastOperation:
    def test_no_operations_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        mock_history.get_operations.return_value = []
        manager = UndoManager(history=mock_history)
        assert manager.undo_last_operation() is False

    def test_operation_with_none_id_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, op_id=None)
        mock_history.get_operations.return_value = [op]
        manager = UndoManager(history=mock_history)
        assert manager.undo_last_operation() is False

    def test_delegates_to_undo_operation(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, op_id=42)
        # First call (get last completed): returns [op]
        # undo_operation internally calls get_operations again
        mock_history.get_operations.return_value = [op]
        mock_validator = MagicMock()
        mock_validator.validate_undo.return_value = ValidationResult(
            can_proceed=False, error_message="conflict"
        )
        manager = UndoManager(history=mock_history, validator=mock_validator)
        # Will fail at validation → False
        result = manager.undo_last_operation()
        assert result is False


# ---------------------------------------------------------------------------
# UndoManager — undo_operation
# ---------------------------------------------------------------------------


class TestUndoManagerUndoOperation:
    def _make_manager(self, operations: list, validate_result: ValidationResult):
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        mock_history.get_operations.return_value = operations
        mock_history.db = MagicMock()
        mock_history.db.execute_query = MagicMock()
        mock_history.db.get_connection.return_value = MagicMock()
        mock_validator = MagicMock()
        mock_validator.validate_undo.return_value = validate_result
        mock_executor = MagicMock()
        mock_executor.rollback_operation.return_value = True
        return UndoManager(history=mock_history, validator=mock_validator, executor=mock_executor)

    def test_operation_not_found_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        mock_history.get_operations.return_value = []
        manager = UndoManager(history=mock_history)
        assert manager.undo_operation(999) is False

    def test_already_rolled_back_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, status=OperationStatus.ROLLED_BACK, op_id=5)
        mock_history.get_operations.return_value = [op]
        manager = UndoManager(history=mock_history)
        assert manager.undo_operation(5) is False

    def test_validation_fails_returns_false(self, tmp_path: Path) -> None:
        op = _make_op(tmp_path, op_id=7)
        vr = ValidationResult(can_proceed=False, error_message="blocked")
        manager = self._make_manager([op], vr)
        assert manager.undo_operation(7) is False

    def test_validation_with_warnings_logs_them(self, tmp_path: Path) -> None:
        op = _make_op(tmp_path, op_id=8)
        vr = ValidationResult(can_proceed=True, warnings=["some warning"])
        manager = self._make_manager([op], vr)
        # executor returns True → success
        result = manager.undo_operation(8)
        assert result is True

    def test_successful_undo_returns_true(self, tmp_path: Path) -> None:
        op = _make_op(tmp_path, op_id=10)
        vr = ValidationResult(can_proceed=True)
        manager = self._make_manager([op], vr)
        result = manager.undo_operation(10)
        assert result is True

    def test_executor_failure_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, op_id=11)
        mock_history.get_operations.return_value = [op]
        mock_validator = MagicMock()
        mock_validator.validate_undo.return_value = ValidationResult(can_proceed=True)
        mock_executor = MagicMock()
        mock_executor.rollback_operation.return_value = False
        manager = UndoManager(
            history=mock_history, validator=mock_validator, executor=mock_executor
        )
        assert manager.undo_operation(11) is False


# ---------------------------------------------------------------------------
# UndoManager — redo_last_operation / redo_operation
# ---------------------------------------------------------------------------


class TestUndoManagerRedoOperation:
    def test_redo_last_no_operations_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        mock_history.get_operations.return_value = []
        manager = UndoManager(history=mock_history)
        assert manager.redo_last_operation() is False

    def test_redo_last_none_id_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, status=OperationStatus.ROLLED_BACK, op_id=None)
        mock_history.get_operations.return_value = [op]
        manager = UndoManager(history=mock_history)
        assert manager.redo_last_operation() is False

    def test_redo_operation_not_found_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        mock_history.get_operations.return_value = []
        manager = UndoManager(history=mock_history)
        assert manager.redo_operation(555) is False

    def test_redo_operation_not_rolled_back_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, status=OperationStatus.COMPLETED, op_id=20)
        mock_history.get_operations.return_value = [op]
        manager = UndoManager(history=mock_history)
        assert manager.redo_operation(20) is False

    def test_redo_validation_fails_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, status=OperationStatus.ROLLED_BACK, op_id=21)
        mock_history.get_operations.return_value = [op]
        mock_validator = MagicMock()
        mock_validator.validate_redo.return_value = ValidationResult(
            can_proceed=False, error_message="redo blocked"
        )
        manager = UndoManager(history=mock_history, validator=mock_validator)
        assert manager.redo_operation(21) is False

    def test_redo_executor_success_returns_true(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, status=OperationStatus.ROLLED_BACK, op_id=22)
        mock_history.get_operations.return_value = [op]
        mock_history.db = MagicMock()
        mock_history.db.execute_query = MagicMock()
        mock_history.db.get_connection.return_value = MagicMock()
        mock_validator = MagicMock()
        mock_validator.validate_redo.return_value = ValidationResult(can_proceed=True)
        mock_executor = MagicMock()
        mock_executor.redo_operation.return_value = True
        manager = UndoManager(
            history=mock_history, validator=mock_validator, executor=mock_executor
        )
        assert manager.redo_operation(22) is True

    def test_redo_executor_failure_returns_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, status=OperationStatus.ROLLED_BACK, op_id=23)
        mock_history.get_operations.return_value = [op]
        mock_validator = MagicMock()
        mock_validator.validate_redo.return_value = ValidationResult(can_proceed=True)
        mock_executor = MagicMock()
        mock_executor.redo_operation.return_value = False
        manager = UndoManager(
            history=mock_history, validator=mock_validator, executor=mock_executor
        )
        assert manager.redo_operation(23) is False


# ---------------------------------------------------------------------------
# UndoManager — can_undo / can_redo
# ---------------------------------------------------------------------------


class TestUndoManagerCanUndoCanRedo:
    def test_can_undo_not_found(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        mock_history.get_operations.return_value = []
        manager = UndoManager(history=mock_history)
        can, reason = manager.can_undo(100)
        assert can is False
        assert "not found" in reason.lower()

    def test_can_undo_already_rolled_back(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, status=OperationStatus.ROLLED_BACK, op_id=2)
        mock_history.get_operations.return_value = [op]
        manager = UndoManager(history=mock_history)
        can, reason = manager.can_undo(2)
        assert can is False
        assert "rolled back" in reason.lower()

    def test_can_undo_validation_passes(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, op_id=3)
        mock_history.get_operations.return_value = [op]
        mock_validator = MagicMock()
        mock_validator.validate_undo.return_value = ValidationResult(can_proceed=True)
        manager = UndoManager(history=mock_history, validator=mock_validator)
        can, reason = manager.can_undo(3)
        assert can is True

    def test_can_undo_validation_fails(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, op_id=4)
        mock_history.get_operations.return_value = [op]
        mock_validator = MagicMock()
        mock_validator.validate_undo.return_value = ValidationResult(
            can_proceed=False, error_message="blocked by conflict"
        )
        manager = UndoManager(history=mock_history, validator=mock_validator)
        can, reason = manager.can_undo(4)
        assert can is False
        assert "conflict" in reason.lower()

    def test_can_redo_not_found(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        mock_history.get_operations.return_value = []
        manager = UndoManager(history=mock_history)
        can, reason = manager.can_redo(200)
        assert can is False
        assert "not found" in reason.lower()

    def test_can_redo_not_rolled_back(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, status=OperationStatus.COMPLETED, op_id=5)
        mock_history.get_operations.return_value = [op]
        manager = UndoManager(history=mock_history)
        can, reason = manager.can_redo(5)
        assert can is False

    def test_can_redo_validation_passes(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, status=OperationStatus.ROLLED_BACK, op_id=6)
        mock_history.get_operations.return_value = [op]
        mock_validator = MagicMock()
        mock_validator.validate_redo.return_value = ValidationResult(can_proceed=True)
        manager = UndoManager(history=mock_history, validator=mock_validator)
        can, reason = manager.can_redo(6)
        assert can is True

    def test_can_redo_validation_fails(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        op = _make_op(tmp_path, status=OperationStatus.ROLLED_BACK, op_id=7)
        mock_history.get_operations.return_value = [op]
        mock_validator = MagicMock()
        mock_validator.validate_redo.return_value = ValidationResult(
            can_proceed=False, error_message=None
        )
        manager = UndoManager(history=mock_history, validator=mock_validator)
        can, reason = manager.can_redo(7)
        assert can is False


# ---------------------------------------------------------------------------
# UndoManager — get_undo_stack / get_redo_stack / context manager
# ---------------------------------------------------------------------------


class TestUndoManagerStacks:
    def test_get_undo_stack_returns_list(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        mock_history.get_operations.return_value = []
        manager = UndoManager(history=mock_history)
        result = manager.get_undo_stack()
        assert result == []

    def test_get_redo_stack_returns_list(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        mock_history.get_operations.return_value = []
        manager = UndoManager(history=mock_history)
        result = manager.get_redo_stack()
        assert result == []

    def test_context_manager_closes_history(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        mock_history = MagicMock()
        manager = UndoManager(history=mock_history)
        with manager:
            pass
        mock_history.close.assert_called_once()
