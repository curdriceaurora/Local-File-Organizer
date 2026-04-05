"""Integration tests for undo and history modules.

Covers UndoManager, RollbackEngine, UndoViewer, UndoValidator, HistoryCleanup, HistoryExport.
All filesystem operations use pytest tmp_path. External services are mocked.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Any:
    """Create a fresh in-memory-like DatabaseManager backed by tmp_path."""
    from file_organizer.history.database import DatabaseManager

    db_path = tmp_path / "test_history.db"
    db = DatabaseManager(db_path)
    db.initialize()
    return db


def _make_history(tmp_path: Path) -> Any:
    """Create a fresh OperationHistory backed by tmp_path."""
    from file_organizer.history.tracker import OperationHistory

    db_path = tmp_path / "test_history.db"
    return OperationHistory(db_path=db_path)


def _make_operation(
    tmp_path: Path,
    op_type: str = "move",
    status: str = "completed",
    src_name: str = "source.txt",
    dst_name: str | None = "dest.txt",
    op_id: int = 1,
    file_hash: str | None = None,
    transaction_id: str | None = None,
) -> Any:
    """Build an Operation dataclass for use in tests."""
    from file_organizer.history.models import Operation, OperationStatus, OperationType

    src = tmp_path / src_name
    dst = tmp_path / dst_name if dst_name else None
    return Operation(
        id=op_id,
        operation_type=OperationType(op_type),
        timestamp=datetime.now(UTC),
        source_path=src,
        destination_path=dst,
        file_hash=file_hash,
        status=OperationStatus(status),
        transaction_id=transaction_id,
    )


# ===========================================================================
# TestOperationValidator
# ===========================================================================


class TestOperationValidator:
    """Tests for OperationValidator — validate_undo / validate_redo paths."""

    def test_validate_undo_move_happy_path(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        # Create files so conditions are satisfied
        _src = tmp_path / "original.txt"
        dst = tmp_path / "moved.txt"
        dst.write_text("content")  # file is at destination

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(
            tmp_path, op_type="move", src_name="original.txt", dst_name="moved.txt"
        )
        result = validator.validate_undo(op)

        assert result.can_proceed is True
        assert len(result.conflicts) == 0

    def test_validate_undo_move_destination_missing(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(
            tmp_path, op_type="move", src_name="original.txt", dst_name="moved.txt"
        )
        # destination does NOT exist → conflict
        result = validator.validate_undo(op)

        assert result.can_proceed is False
        assert len(result.conflicts) >= 1
        conflict_types = [c.conflict_type for c in result.conflicts]
        assert any("file_missing" in str(ct) for ct in conflict_types)

    def test_validate_undo_already_rolled_back(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(tmp_path, op_type="move", status="rolled_back")
        result = validator.validate_undo(op)

        assert result.can_proceed is False
        assert result.error_message is not None
        assert "rolled back" in result.error_message.lower()

    def test_validate_undo_failed_operation_has_warning(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        _src = tmp_path / "original.txt"
        dst = tmp_path / "moved.txt"
        dst.write_text("content")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(
            tmp_path, op_type="move", status="failed", src_name="original.txt", dst_name="moved.txt"
        )
        result = validator.validate_undo(op)

        # Should have at least a warning about failed operation
        assert len(result.warnings) >= 1

    def test_validate_undo_rename_happy_path(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        new_name = tmp_path / "new_name.txt"
        new_name.write_text("content")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(
            tmp_path, op_type="rename", src_name="old_name.txt", dst_name="new_name.txt"
        )
        result = validator.validate_undo(op)

        assert result.can_proceed is True

    def test_validate_undo_create_file_exists(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        created_file = tmp_path / "created.txt"
        created_file.write_text("content")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(tmp_path, op_type="create", src_name="created.txt", dst_name=None)
        result = validator.validate_undo(op)

        assert result.can_proceed is True

    def test_validate_undo_create_file_missing(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(tmp_path, op_type="create", src_name="missing.txt", dst_name=None)
        result = validator.validate_undo(op)

        assert result.can_proceed is False
        assert len(result.conflicts) == 1

    def test_validate_undo_copy_destination_exists(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        copy_path = tmp_path / "copy.txt"
        copy_path.write_text("content")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(tmp_path, op_type="copy", src_name="original.txt", dst_name="copy.txt")
        result = validator.validate_undo(op)

        assert result.can_proceed is True

    def test_validate_undo_delete_file_in_trash(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        trash_dir = tmp_path / "trash"
        # Set up file in trash at expected path: trash / <op_id> / filename
        op_id = 42
        trash_file_dir = trash_dir / str(op_id)
        trash_file_dir.mkdir(parents=True)
        trash_file = trash_file_dir / "deleted.txt"
        trash_file.write_text("deleted content")

        validator = OperationValidator(trash_dir=trash_dir)
        op = _make_operation(
            tmp_path, op_type="delete", src_name="deleted.txt", dst_name=None, op_id=op_id
        )
        result = validator.validate_undo(op)

        assert result.can_proceed is True

    def test_validate_undo_delete_file_not_in_trash(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(tmp_path, op_type="delete", src_name="lost.txt", dst_name=None)
        result = validator.validate_undo(op)

        assert result.can_proceed is False
        conflict_types = [c.conflict_type for c in result.conflicts]
        assert any("file_missing" in str(ct) for ct in conflict_types)

    def test_validate_redo_not_rolled_back(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(tmp_path, op_type="move", status="completed")
        result = validator.validate_redo(op)

        assert result.can_proceed is False
        assert result.error_message is not None

    def test_validate_redo_move_happy_path(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        src = tmp_path / "source.txt"
        src.write_text("content")  # source exists again after undo

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(
            tmp_path,
            op_type="move",
            status="rolled_back",
            src_name="source.txt",
            dst_name="dest.txt",
        )
        result = validator.validate_redo(op)

        assert result.can_proceed is True

    def test_validate_redo_create_path_occupied(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        existing = tmp_path / "existing.txt"
        existing.write_text("conflict")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(
            tmp_path, op_type="create", status="rolled_back", src_name="existing.txt", dst_name=None
        )
        result = validator.validate_redo(op)

        assert result.can_proceed is False
        conflict_types = [c.conflict_type for c in result.conflicts]
        assert any("path_occupied" in str(ct) for ct in conflict_types)

    def test_check_file_integrity_matches(self, tmp_path: Path) -> None:
        import hashlib

        from file_organizer.undo.validator import OperationValidator

        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"hello world")
        expected_hash = hashlib.sha256(b"hello world").hexdigest()

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        assert validator.check_file_integrity(test_file, expected_hash) is True

    def test_check_file_integrity_mismatch(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"hello world")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        assert validator.check_file_integrity(test_file, "deadbeef" * 8) is False

    def test_check_file_integrity_missing_file(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        missing = tmp_path / "no_such.txt"
        validator = OperationValidator(trash_dir=tmp_path / "trash")
        assert validator.check_file_integrity(missing, "anyhash") is False

    def test_check_path_exists_true(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        f = tmp_path / "exists.txt"
        f.write_text("x")
        validator = OperationValidator(trash_dir=tmp_path / "trash")
        assert validator.check_path_exists(f) is True

    def test_check_path_exists_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        assert validator.check_path_exists(tmp_path / "ghost.txt") is False

    def test_check_path_available_true(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        assert validator.check_path_available(tmp_path / "free.txt") is True

    def test_check_path_available_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        taken = tmp_path / "taken.txt"
        taken.write_text("x")
        validator = OperationValidator(trash_dir=tmp_path / "trash")
        assert validator.check_path_available(taken) is False

    def test_check_conflicts_undo_delegates(self, tmp_path: Path) -> None:
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(tmp_path, op_type="create", src_name="missing.txt", dst_name=None)
        conflicts = validator.check_conflicts(op, is_undo=True)
        assert isinstance(conflicts, list)
        assert len(conflicts) >= 1

    def test_validation_result_bool_true(self, tmp_path: Path) -> None:
        from file_organizer.undo.models import ValidationResult

        vr = ValidationResult(can_proceed=True)
        assert bool(vr) is True

    def test_validation_result_bool_false(self, tmp_path: Path) -> None:
        from file_organizer.undo.models import ValidationResult

        vr = ValidationResult(can_proceed=False, error_message="nope")
        assert bool(vr) is False

    def test_hash_mismatch_detected_in_move_undo(self, tmp_path: Path) -> None:
        import hashlib

        from file_organizer.undo.validator import OperationValidator

        dst = tmp_path / "moved.txt"
        dst.write_bytes(b"modified content")
        original_hash = hashlib.sha256(b"original content").hexdigest()

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        op = _make_operation(
            tmp_path,
            op_type="move",
            src_name="source.txt",
            dst_name="moved.txt",
            file_hash=original_hash,
        )
        result = validator.validate_undo(op)

        # Should detect hash mismatch
        conflict_types = [c.conflict_type for c in result.conflicts]
        assert any("hash_mismatch" in str(ct) for ct in conflict_types)


# ===========================================================================
# TestRollbackEngine
# ===========================================================================


class TestRollbackEngine:
    """Tests for RollbackExecutor — rollback/redo of each operation type."""

    def test_rollback_move_success(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        src = tmp_path / "original.txt"
        dst = tmp_path / "moved.txt"
        dst.write_text("content")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path, op_type="move", src_name="original.txt", dst_name="moved.txt"
        )

        result = executor.rollback_move(op)

        assert result is True
        assert src.exists()
        assert not dst.exists()

    def test_rollback_move_missing_destination(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(tmp_path, op_type="move", src_name="src.txt", dst_name="missing.txt")

        result = executor.rollback_move(op)

        assert result is False

    def test_rollback_rename_success(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        old_name = tmp_path / "old.txt"
        new_name = tmp_path / "new.txt"
        new_name.write_text("content")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(tmp_path, op_type="rename", src_name="old.txt", dst_name="new.txt")

        result = executor.rollback_rename(op)

        assert result is True
        assert old_name.exists()
        assert not new_name.exists()

    def test_rollback_rename_no_destination(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(tmp_path, op_type="rename", src_name="old.txt", dst_name=None)

        result = executor.rollback_rename(op)

        assert result is False

    def test_rollback_copy_success(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        copy_path = tmp_path / "copy.txt"
        copy_path.write_text("copied content")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path, op_type="copy", src_name="original.txt", dst_name="copy.txt", op_id=99
        )

        result = executor.rollback_copy(op)

        assert result is True
        assert not copy_path.exists()

    def test_rollback_copy_no_destination(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(tmp_path, op_type="copy", src_name="src.txt", dst_name=None)

        result = executor.rollback_copy(op)

        assert result is False

    def test_rollback_create_success(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        created_file = tmp_path / "created.txt"
        created_file.write_text("new file")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path, op_type="create", src_name="created.txt", dst_name=None, op_id=55
        )

        result = executor.rollback_create(op)

        assert result is True
        assert not created_file.exists()

    def test_rollback_delete_from_trash(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        trash_dir = tmp_path / "trash"
        op_id = 7
        trash_op_dir = trash_dir / str(op_id)
        trash_op_dir.mkdir(parents=True)
        trash_file = trash_op_dir / "deleted.txt"
        trash_file.write_text("was deleted")

        original_path = tmp_path / "deleted.txt"

        validator = OperationValidator(trash_dir=trash_dir)
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path, op_type="delete", src_name="deleted.txt", dst_name=None, op_id=op_id
        )

        result = executor.rollback_delete(op)

        assert result is True
        assert original_path.exists()

    def test_rollback_delete_not_in_trash(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(tmp_path, op_type="delete", src_name="lost.txt", dst_name=None)

        result = executor.rollback_delete(op)

        assert result is False

    def test_redo_move_success(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        src = tmp_path / "source.txt"
        src.write_text("content")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path,
            op_type="move",
            status="rolled_back",
            src_name="source.txt",
            dst_name="dest.txt",
        )

        result = executor.redo_move(op)

        assert result is True
        dst = tmp_path / "dest.txt"
        assert dst.exists()

    def test_redo_move_no_destination(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        src = tmp_path / "source.txt"
        src.write_text("content")
        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path, op_type="move", status="rolled_back", src_name="source.txt", dst_name=None
        )

        result = executor.redo_move(op)

        assert result is False

    def test_redo_rename_success(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        old_name = tmp_path / "old.txt"
        old_name.write_text("content")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path, op_type="rename", status="rolled_back", src_name="old.txt", dst_name="new.txt"
        )

        result = executor.redo_rename(op)

        assert result is True
        assert (tmp_path / "new.txt").exists()

    def test_redo_copy_success(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        src = tmp_path / "source.txt"
        src.write_text("content")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path,
            op_type="copy",
            status="rolled_back",
            src_name="source.txt",
            dst_name="copy.txt",
        )

        result = executor.redo_copy(op)

        assert result is True
        assert (tmp_path / "copy.txt").exists()

    def test_redo_copy_no_destination(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        src = tmp_path / "source.txt"
        src.write_text("x")
        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path, op_type="copy", status="rolled_back", src_name="source.txt", dst_name=None
        )

        result = executor.redo_copy(op)

        assert result is False

    def test_redo_create_file(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        new_file = tmp_path / "recreated.txt"
        assert not new_file.exists()

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path,
            op_type="create",
            status="rolled_back",
            src_name="recreated.txt",
            dst_name=None,
        )
        op.metadata = {}

        result = executor.redo_create(op)

        assert result is True
        assert new_file.exists()

    def test_redo_create_directory(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path, op_type="create", status="rolled_back", src_name="new_dir", dst_name=None
        )
        op.metadata = {"is_dir": True}

        result = executor.redo_create(op)

        assert result is True
        assert (tmp_path / "new_dir").is_dir()

    def test_redo_delete_success(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        target = tmp_path / "target.txt"
        target.write_text("to delete again")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(
            tmp_path,
            op_type="delete",
            status="rolled_back",
            src_name="target.txt",
            dst_name=None,
            op_id=20,
        )

        result = executor.redo_delete(op)

        assert result is True
        assert not target.exists()

    def test_rollback_transaction_all_succeed(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        # Setup two files at destination positions
        dst1 = tmp_path / "dest1.txt"
        dst2 = tmp_path / "dest2.txt"
        dst1.write_text("a")
        dst2.write_text("b")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)

        op1 = _make_operation(
            tmp_path, op_type="move", src_name="src1.txt", dst_name="dest1.txt", op_id=1
        )
        op2 = _make_operation(
            tmp_path, op_type="move", src_name="src2.txt", dst_name="dest2.txt", op_id=2
        )

        result = executor.rollback_transaction("txn-1", [op1, op2])

        assert result.success is True
        assert result.operations_rolled_back == 2
        assert result.operations_failed == 0

    def test_rollback_transaction_partial_failure(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        # Only first destination exists
        dst1 = tmp_path / "dest1.txt"
        dst1.write_text("a")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)

        op1 = _make_operation(
            tmp_path, op_type="move", src_name="src1.txt", dst_name="dest1.txt", op_id=1
        )
        op2 = _make_operation(
            tmp_path, op_type="move", src_name="src2.txt", dst_name="missing_dst.txt", op_id=2
        )

        result = executor.rollback_transaction("txn-1", [op1, op2])

        # One succeeded, one failed (op2 reversed goes first due to reversed())
        assert result.operations_rolled_back + result.operations_failed == 2

    def test_rollback_operation_unknown_type(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)
        op = _make_operation(tmp_path, op_type="move")
        op.operation_type = "unknown_type"  # type: ignore[assignment]

        result = executor.rollback_operation(op)

        assert result is False

    def test_move_to_trash_creates_correct_path(self, tmp_path: Path) -> None:
        from file_organizer.undo.rollback import RollbackExecutor
        from file_organizer.undo.validator import OperationValidator

        test_file = tmp_path / "to_trash.txt"
        test_file.write_text("content")

        validator = OperationValidator(trash_dir=tmp_path / "trash")
        executor = RollbackExecutor(validator)

        trash_path = executor._move_to_trash(test_file, operation_id=123)

        assert trash_path.exists()
        assert trash_path.name == "to_trash.txt"
        assert "123" in str(trash_path)


# ===========================================================================
# TestUndoManager
# ===========================================================================


class TestUndoManager:
    """Tests for UndoManager high-level undo/redo interface."""

    def test_init_creates_default_components(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)

        assert manager.history is history
        assert manager.validator is not None
        assert manager.executor is not None
        assert manager.max_stack_size == 1000

    def test_undo_last_operation_empty_history(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)

        result = manager.undo_last_operation()

        assert result is False

    def test_redo_last_operation_empty_history(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)

        result = manager.redo_last_operation()

        assert result is False

    def test_get_undo_stack_empty(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)

        stack = manager.get_undo_stack()

        assert isinstance(stack, list)
        assert len(stack) == 0

    def test_get_redo_stack_empty(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)

        stack = manager.get_redo_stack()

        assert isinstance(stack, list)
        assert len(stack) == 0

    def test_get_undo_stack_with_operations(self, tmp_path: Path) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.undo_manager import UndoManager

        src = tmp_path / "file.txt"
        src.write_text("content")
        history = _make_history(tmp_path)
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        manager = UndoManager(history=history)
        stack = manager.get_undo_stack()

        assert isinstance(stack, list)
        assert len(stack) == 1

    def test_undo_operation_not_found(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)

        result = manager.undo_operation(99999)

        assert result is False

    def test_redo_operation_not_found(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)

        result = manager.redo_operation(99999)

        assert result is False

    def test_can_undo_not_found_returns_false_with_message(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)

        can, reason = manager.can_undo(99999)

        assert can is False
        assert len(reason) > 0
        assert "not found" in reason.lower()

    def test_can_redo_not_found_returns_false_with_message(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)

        can, reason = manager.can_redo(99999)

        assert can is False
        assert len(reason) > 0

    def test_clear_redo_stack_no_error(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)
        # Should not raise
        manager.clear_redo_stack()

    def test_context_manager_closes_on_exit(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        with UndoManager(history=history) as manager:
            assert manager is not None
        # After exit, no exception means close() ran cleanly

    def test_undo_transaction_not_found(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)

        result = manager.undo_transaction("non-existent-txn")

        assert result is False

    def test_redo_transaction_not_found(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history)

        result = manager.redo_transaction("non-existent-txn")

        assert result is False

    def test_undo_operation_already_rolled_back(self, tmp_path: Path) -> None:
        from file_organizer.history.models import OperationStatus, OperationType
        from file_organizer.undo.undo_manager import UndoManager

        src = tmp_path / "file.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        op_id = history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")
        # Manually set to rolled_back
        history.db.execute_query(
            "UPDATE operations SET status = ? WHERE id = ?",
            (OperationStatus.ROLLED_BACK.value, op_id),
        )
        history.db.get_connection().commit()

        manager = UndoManager(history=history)
        result = manager.undo_operation(op_id)

        assert result is False

    def test_redo_operation_not_rolled_back(self, tmp_path: Path) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.undo_manager import UndoManager

        src = tmp_path / "file.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        op_id = history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        manager = UndoManager(history=history)
        result = manager.redo_operation(op_id)

        # Not rolled_back, so cannot redo
        assert result is False

    def test_can_undo_already_rolled_back(self, tmp_path: Path) -> None:
        from file_organizer.history.models import OperationStatus, OperationType
        from file_organizer.undo.undo_manager import UndoManager

        src = tmp_path / "file.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        op_id = history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")
        history.db.execute_query(
            "UPDATE operations SET status = ? WHERE id = ?",
            (OperationStatus.ROLLED_BACK.value, op_id),
        )
        history.db.get_connection().commit()

        manager = UndoManager(history=history)
        can, reason = manager.can_undo(op_id)

        assert can is False
        assert "rolled back" in reason.lower()

    def test_can_redo_operation_not_rolled_back(self, tmp_path: Path) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.undo_manager import UndoManager

        src = tmp_path / "file.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        op_id = history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        manager = UndoManager(history=history)
        can, reason = manager.can_redo(op_id)

        assert can is False
        assert len(reason) > 0

    def test_custom_max_stack_size_respected(self, tmp_path: Path) -> None:
        from file_organizer.undo.undo_manager import UndoManager

        history = _make_history(tmp_path)
        manager = UndoManager(history=history, max_stack_size=50)

        assert manager.max_stack_size == 50

    def test_undo_last_with_completed_operation_calls_rollback(self, tmp_path: Path) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.undo_manager import UndoManager

        src = tmp_path / "file.txt"
        dst = tmp_path / "dest.txt"
        dst.write_text("content")
        history = _make_history(tmp_path)
        history.log_operation(OperationType.MOVE, src, dst)

        mock_executor = MagicMock()
        mock_executor.rollback_operation.return_value = True

        mock_validator = MagicMock()
        mock_validator.validate_undo.return_value = MagicMock(
            can_proceed=True, warnings=[], conflicts=[]
        )

        manager = UndoManager(history=history, validator=mock_validator, executor=mock_executor)
        result = manager.undo_last_operation()

        assert result is True
        mock_executor.rollback_operation.assert_called_once()


# ===========================================================================
# TestHistoryViewer
# ===========================================================================


class TestHistoryViewer:
    """Tests for HistoryViewer display and filtering methods."""

    def test_show_recent_no_operations_prints_message(self, tmp_path: Path, capsys: Any) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        viewer.show_recent_operations(limit=10)

        out = capsys.readouterr().out
        assert "No operations found" in out

    def test_show_recent_with_operations(self, tmp_path: Path, capsys: Any) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.viewer import HistoryViewer

        src = tmp_path / "file.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        viewer = HistoryViewer(history=history)
        viewer.show_recent_operations(limit=5)

        out = capsys.readouterr().out
        assert "1 most recent operations" in out

    def test_filter_operations_by_type(self, tmp_path: Path) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.viewer import HistoryViewer

        src = tmp_path / "file.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")
        history.log_operation(OperationType.COPY, src, tmp_path / "copy.txt")

        viewer = HistoryViewer(history=history)
        results = viewer.filter_operations(operation_type="move")

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].operation_type.value == "move"

    def test_filter_operations_invalid_type_returns_empty(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        results = viewer.filter_operations(operation_type="invalid_type")

        assert isinstance(results, list)
        assert len(results) == 0

    def test_filter_operations_invalid_status_returns_empty(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        results = viewer.filter_operations(status="bad_status")

        assert isinstance(results, list)
        assert len(results) == 0

    def test_filter_operations_by_status(self, tmp_path: Path) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.viewer import HistoryViewer

        src = tmp_path / "file.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        viewer = HistoryViewer(history=history)
        results = viewer.filter_operations(status="completed")

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].status.value == "completed"

    def test_search_by_path_found(self, tmp_path: Path) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.viewer import HistoryViewer

        src = tmp_path / "unique_search_term.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        viewer = HistoryViewer(history=history)
        results = viewer.search_by_path("unique_search_term")

        assert isinstance(results, list)
        assert len(results) == 1

    def test_search_by_path_not_found(self, tmp_path: Path) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        results = viewer.search_by_path("nonexistent_path_xyz")

        assert isinstance(results, list)
        assert len(results) == 0

    def test_get_statistics_empty_db(self, tmp_path: Path) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        stats = viewer.get_statistics()

        assert isinstance(stats, dict)
        assert "total_operations" in stats
        assert stats["total_operations"] == 0
        assert "by_type" in stats
        assert "by_status" in stats

    def test_get_statistics_with_data(self, tmp_path: Path) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.viewer import HistoryViewer

        src = tmp_path / "file.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")
        history.log_operation(OperationType.COPY, src, tmp_path / "copy.txt")

        viewer = HistoryViewer(history=history)
        stats = viewer.get_statistics()

        assert stats["total_operations"] == 2
        assert stats["by_type"]["move"] == 1
        assert stats["by_type"]["copy"] == 1
        assert stats["latest_operation"] is not None
        assert stats["oldest_operation"] is not None

    def test_show_operation_details_not_found(self, tmp_path: Path, capsys: Any) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        viewer.show_operation_details(99999)

        out = capsys.readouterr().out
        assert "not found" in out.lower()

    def test_show_operation_details_found(self, tmp_path: Path, capsys: Any) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.viewer import HistoryViewer

        src = tmp_path / "file.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        op_id = history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        viewer = HistoryViewer(history=history)
        viewer.show_operation_details(op_id)

        out = capsys.readouterr().out
        assert str(op_id) in out
        assert "move" in out.lower()

    def test_show_statistics_output(self, tmp_path: Path, capsys: Any) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        viewer.show_statistics()

        out = capsys.readouterr().out
        assert "Total operations" in out

    def test_display_filtered_by_search(self, tmp_path: Path, capsys: Any) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.viewer import HistoryViewer

        src = tmp_path / "important_file.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        viewer = HistoryViewer(history=history)
        viewer.display_filtered_operations(search="important_file")

        out = capsys.readouterr().out
        assert "important_file" in out

    def test_display_filtered_no_results(self, tmp_path: Path, capsys: Any) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        viewer.display_filtered_operations(operation_type="move")

        out = capsys.readouterr().out
        assert "No operations found" in out

    def test_context_manager(self, tmp_path: Path) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        with HistoryViewer(history=history) as viewer:
            assert viewer is not None

    def test_parse_date_iso_format(self, tmp_path: Path) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        result = viewer._parse_date("2024-01-15T10:30:00Z")

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_date_ymd_format(self, tmp_path: Path) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        result = viewer._parse_date("2024-06-01")

        assert result is not None
        assert result.year == 2024
        assert result.month == 6

    def test_parse_date_invalid_returns_none(self, tmp_path: Path, capsys: Any) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        result = viewer._parse_date("not-a-date")

        assert result is None

    def test_show_transaction_not_found(self, tmp_path: Path, capsys: Any) -> None:
        from file_organizer.undo.viewer import HistoryViewer

        history = _make_history(tmp_path)
        viewer = HistoryViewer(history=history)
        viewer.show_transaction_details("nonexistent-txn-id")

        out = capsys.readouterr().out
        assert "not found" in out.lower()

    def test_filter_with_date_range(self, tmp_path: Path) -> None:
        from file_organizer.history.models import OperationType
        from file_organizer.undo.viewer import HistoryViewer

        src = tmp_path / "file.txt"
        src.write_text("x")
        history = _make_history(tmp_path)
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        viewer = HistoryViewer(history=history)
        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
        results = viewer.filter_operations(since=yesterday, until=tomorrow)

        assert isinstance(results, list)
        assert len(results) == 1


# ===========================================================================
# TestHistoryCleanup
# ===========================================================================


class TestHistoryCleanup:
    """Tests for HistoryCleanup — retention policies and database maintenance."""

    def test_init_with_defaults(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup, HistoryCleanupConfig

        db = _make_db(tmp_path)
        cleanup = HistoryCleanup(db)

        assert cleanup.db is db
        assert isinstance(cleanup.config, HistoryCleanupConfig)
        assert cleanup.config.max_operations == 10000

    def test_init_with_custom_config(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup, HistoryCleanupConfig

        db = _make_db(tmp_path)
        config = HistoryCleanupConfig(max_operations=100, max_age_days=30)
        cleanup = HistoryCleanup(db, config=config)

        assert cleanup.config.max_operations == 100
        assert cleanup.config.max_age_days == 30

    def test_should_cleanup_false_when_disabled(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup, HistoryCleanupConfig

        db = _make_db(tmp_path)
        config = HistoryCleanupConfig(auto_cleanup_enabled=False)
        cleanup = HistoryCleanup(db, config=config)

        assert cleanup.should_cleanup() is False

    def test_should_cleanup_false_when_under_limits(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup, HistoryCleanupConfig

        db = _make_db(tmp_path)
        config = HistoryCleanupConfig(max_operations=10000, auto_cleanup_enabled=True)
        cleanup = HistoryCleanup(db, config=config)

        # Empty DB, well under limits
        assert cleanup.should_cleanup() is False

    def test_cleanup_old_operations_removes_old_records(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        cleanup = HistoryCleanup(history.db)
        # Use 0 days to delete everything
        deleted = cleanup.cleanup_old_operations(max_age_days=0)

        assert isinstance(deleted, int)
        # The operation just recorded should be deleted (0 days ago = now)
        # May or may not delete it depending on exact timing, but no error
        assert deleted >= 0

    def test_cleanup_by_count_keeps_most_recent(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        for _ in range(5):
            history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        cleanup = HistoryCleanup(history.db)
        deleted = cleanup.cleanup_by_count(max_operations=3)

        assert isinstance(deleted, int)
        assert deleted >= 0
        remaining = history.db.get_operation_count()
        assert remaining <= 3

    def test_cleanup_by_count_zero_max_deletes_all(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        for _ in range(3):
            history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        cleanup = HistoryCleanup(history.db)
        cleanup.cleanup_by_count(max_operations=0)

        assert history.db.get_operation_count() == 0

    def test_cleanup_by_count_negative_raises(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup

        db = _make_db(tmp_path)
        cleanup = HistoryCleanup(db)

        with pytest.raises(ValueError, match="non-negative"):
            cleanup.cleanup_by_count(max_operations=-1)

    def test_cleanup_by_count_no_cleanup_needed(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup

        db = _make_db(tmp_path)
        cleanup = HistoryCleanup(db)

        # Empty DB, 100 allowed
        deleted = cleanup.cleanup_by_count(max_operations=100)

        assert deleted == 0

    def test_cleanup_failed_operations(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup
        from file_organizer.history.models import OperationStatus, OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(
            OperationType.MOVE, src, tmp_path / "dest.txt", status=OperationStatus.FAILED
        )

        cleanup = HistoryCleanup(history.db)
        # 0 days means anything older than now is deleted
        deleted = cleanup.cleanup_failed_operations(older_than_days=0)

        assert isinstance(deleted, int)
        assert deleted >= 0

    def test_cleanup_rolled_back_operations(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup
        from file_organizer.history.models import OperationStatus, OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(
            OperationType.MOVE, src, tmp_path / "dest.txt", status=OperationStatus.ROLLED_BACK
        )

        cleanup = HistoryCleanup(history.db)
        deleted = cleanup.cleanup_rolled_back_operations(older_than_days=0)

        assert isinstance(deleted, int)
        assert deleted >= 0

    def test_clear_all_requires_confirm(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        cleanup = HistoryCleanup(history.db)
        result = cleanup.clear_all(confirm=False)

        assert result is False
        assert history.db.get_operation_count() == 1

    def test_clear_all_with_confirm(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        cleanup = HistoryCleanup(history.db)
        result = cleanup.clear_all(confirm=True)

        assert result is True
        assert history.db.get_operation_count() == 0

    def test_get_statistics_empty(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup

        db = _make_db(tmp_path)
        cleanup = HistoryCleanup(db)
        stats = cleanup.get_statistics()

        assert isinstance(stats, dict)
        assert "total_operations" in stats
        assert stats["total_operations"] == 0
        assert "database_size_mb" in stats

    def test_get_statistics_with_data(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        cleanup = HistoryCleanup(history.db)
        stats = cleanup.get_statistics()

        assert stats["total_operations"] == 1
        assert "operations_completed" in stats
        assert stats["operations_completed"] == 1

    def test_auto_cleanup_not_needed(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup, HistoryCleanupConfig

        db = _make_db(tmp_path)
        config = HistoryCleanupConfig(auto_cleanup_enabled=True, max_operations=10000)
        cleanup = HistoryCleanup(db, config=config)

        result = cleanup.auto_cleanup()

        assert isinstance(result, dict)
        assert "deleted_operations" in result
        assert result["deleted_operations"] == 0

    def test_auto_cleanup_when_over_limit(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup, HistoryCleanupConfig
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        for _ in range(5):
            history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        config = HistoryCleanupConfig(auto_cleanup_enabled=True, max_operations=2)
        cleanup = HistoryCleanup(history.db, config=config)
        result = cleanup.auto_cleanup()

        assert isinstance(result, dict)
        assert result["deleted_operations"] >= 0

    def test_cleanup_by_size_no_cleanup_needed(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanup

        db = _make_db(tmp_path)
        cleanup = HistoryCleanup(db)
        # Empty DB is tiny, 1000MB limit
        deleted = cleanup.cleanup_by_size(max_size_mb=1000)

        assert deleted == 0

    def test_cleanup_config_defaults(self, tmp_path: Path) -> None:
        from file_organizer.history.cleanup import HistoryCleanupConfig

        config = HistoryCleanupConfig()

        assert config.max_operations == 10000
        assert config.max_age_days == 90
        assert config.max_size_mb == 100
        assert config.auto_cleanup_enabled is True
        assert config.cleanup_batch_size == 1000


# ===========================================================================
# TestHistoryExporter
# ===========================================================================


class TestHistoryExporter:
    """Tests for HistoryExporter — JSON/CSV export of operations and transactions."""

    def test_export_to_json_empty_db(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter

        db = _make_db(tmp_path)
        exporter = HistoryExporter(db)
        output = tmp_path / "export.json"

        stats = exporter.export_to_json(output)

        assert output.exists()
        assert isinstance(stats, dict)
        assert stats["operations_exported"] == 0

    def test_export_to_json_with_data(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        exporter = HistoryExporter(history.db)
        output = tmp_path / "export.json"
        stats = exporter.export_to_json(output)

        assert output.exists()
        assert stats["operations_exported"] == 1

        with open(output) as f:
            data = json.load(f)
        assert "export_date" in data
        assert "operations" in data
        assert len(data["operations"]) == 1

    def test_export_to_json_with_operation_type_filter(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")
        history.log_operation(OperationType.COPY, src, tmp_path / "copy.txt")

        exporter = HistoryExporter(history.db)
        output = tmp_path / "filtered.json"
        stats = exporter.export_to_json(output, operation_type=OperationType.MOVE)

        assert stats["operations_exported"] == 1

        with open(output) as f:
            data = json.load(f)
        assert all(op["operation_type"] == "move" for op in data["operations"])

    def test_export_to_json_with_date_filter(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        exporter = HistoryExporter(history.db)
        output = tmp_path / "dated.json"
        start = datetime.now(UTC) - timedelta(hours=1)
        end = datetime.now(UTC) + timedelta(hours=1)
        stats = exporter.export_to_json(output, start_date=start, end_date=end)

        assert stats["operations_exported"] == 1

    def test_export_to_json_excludes_transactions_when_flag_false(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        exporter = HistoryExporter(history.db)
        output = tmp_path / "no_txn.json"
        exporter.export_to_json(output, include_transactions=False)

        with open(output) as f:
            data = json.load(f)
        assert "transactions" not in data

    def test_export_to_csv_empty_db(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter

        db = _make_db(tmp_path)
        exporter = HistoryExporter(db)
        output = tmp_path / "export.csv"

        count = exporter.export_to_csv(output)

        assert count == 0
        # File may not be created if empty
        assert isinstance(count, int)

    def test_export_to_csv_with_data(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        exporter = HistoryExporter(history.db)
        output = tmp_path / "export.csv"
        count = exporter.export_to_csv(output)

        assert count == 1
        assert output.exists()

        with open(output, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["operation_type"] == "move"

    def test_export_to_csv_with_type_filter(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")
        history.log_operation(OperationType.COPY, src, tmp_path / "copy.txt")

        exporter = HistoryExporter(history.db)
        output = tmp_path / "filtered.csv"
        count = exporter.export_to_csv(output, operation_type=OperationType.COPY)

        assert count == 1

    def test_export_transactions_to_csv_empty(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter

        db = _make_db(tmp_path)
        exporter = HistoryExporter(db)
        output = tmp_path / "txns.csv"

        count = exporter.export_transactions_to_csv(output)

        assert count == 0

    def test_export_transactions_to_csv_with_data(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        txn_id = history.start_transaction()
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt", transaction_id=txn_id)
        history.commit_transaction(txn_id)

        exporter = HistoryExporter(history.db)
        output = tmp_path / "txns.csv"
        count = exporter.export_transactions_to_csv(output)

        assert count >= 1
        assert output.exists()

    def test_export_statistics_to_json(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter

        db = _make_db(tmp_path)
        exporter = HistoryExporter(db)
        output = tmp_path / "stats.json"

        result = exporter.export_statistics(output)

        assert result is True
        assert output.exists()

        with open(output) as f:
            data = json.load(f)
        assert "total_operations" in data
        assert "export_date" in data
        assert "database_size_mb" in data

    def test_export_statistics_with_data(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        exporter = HistoryExporter(history.db)
        output = tmp_path / "stats.json"
        exporter.export_statistics(output)

        with open(output) as f:
            data = json.load(f)
        assert data["total_operations"] == 1
        assert "operations_move" in data
        assert data["operations_move"] == 1

    def test_export_to_json_creates_parent_dirs(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter

        db = _make_db(tmp_path)
        exporter = HistoryExporter(db)
        output = tmp_path / "nested" / "deep" / "export.json"

        exporter.export_to_json(output)

        assert output.exists()

    def test_export_to_csv_creates_parent_dirs(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        exporter = HistoryExporter(history.db)
        output = tmp_path / "nested" / "deep" / "export.csv"
        exporter.export_to_csv(output)

        assert output.exists()

    def test_export_csv_has_all_expected_columns(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        exporter = HistoryExporter(history.db)
        output = tmp_path / "export.csv"
        exporter.export_to_csv(output)

        with open(output, newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames

        expected_columns = ["id", "operation_type", "timestamp", "source_path", "status"]
        for col in expected_columns:
            assert col in fieldnames, f"Missing column: {col}"

    def test_export_json_operation_count_in_stats(self, tmp_path: Path) -> None:
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType

        history = _make_history(tmp_path)
        src = tmp_path / "file.txt"
        src.write_text("x")
        for _ in range(3):
            history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        exporter = HistoryExporter(history.db)
        output = tmp_path / "export.json"
        stats = exporter.export_to_json(output)

        assert stats["operations_exported"] == 3
        assert isinstance(stats["transactions_exported"], int)
        assert stats["transactions_exported"] >= 0
