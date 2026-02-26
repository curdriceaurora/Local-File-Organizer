"""Tests for undo/redo data models.

Covers Conflict, ValidationResult, and RollbackResult string representations
and boolean behaviors.
"""

from __future__ import annotations

import unittest

from file_organizer.undo.models import (
    Conflict,
    ConflictType,
    RollbackResult,
    ValidationResult,
)


class TestConflictType(unittest.TestCase):
    """Test ConflictType enum."""

    def test_values(self):
        self.assertEqual(ConflictType.FILE_MODIFIED, "file_modified")
        self.assertEqual(ConflictType.FILE_MISSING, "file_missing")
        self.assertEqual(ConflictType.PATH_OCCUPIED, "path_occupied")
        self.assertEqual(ConflictType.PERMISSION_DENIED, "permission_denied")
        self.assertEqual(ConflictType.DISK_SPACE, "disk_space")
        self.assertEqual(ConflictType.PARENT_MISSING, "parent_missing")
        self.assertEqual(ConflictType.HASH_MISMATCH, "hash_mismatch")


class TestConflict(unittest.TestCase):
    """Test Conflict dataclass."""

    def test_str_basic(self):
        c = Conflict(
            conflict_type=ConflictType.FILE_MISSING,
            path="/some/path",
            description="File not found",
        )
        s = str(c)
        self.assertIn("file_missing", s)
        self.assertIn("/some/path", s)
        self.assertIn("File not found", s)

    def test_str_with_expected_actual(self):
        c = Conflict(
            conflict_type=ConflictType.HASH_MISMATCH,
            path="/file.txt",
            description="Hash differs",
            expected="abc123",
            actual="def456",
        )
        s = str(c)
        self.assertIn("expected: abc123", s)
        self.assertIn("actual: def456", s)

    def test_str_without_expected_actual(self):
        c = Conflict(
            conflict_type=ConflictType.FILE_MISSING,
            path="/file.txt",
            description="missing",
        )
        s = str(c)
        self.assertNotIn("expected:", s)


class TestValidationResult(unittest.TestCase):
    """Test ValidationResult dataclass."""

    def test_bool_true(self):
        vr = ValidationResult(can_proceed=True)
        self.assertTrue(bool(vr))

    def test_bool_false(self):
        vr = ValidationResult(can_proceed=False)
        self.assertFalse(bool(vr))

    def test_str_passed(self):
        vr = ValidationResult(can_proceed=True)
        s = str(vr)
        self.assertIn("Validation passed", s)

    def test_str_passed_with_warnings(self):
        vr = ValidationResult(
            can_proceed=True, warnings=["warn1", "warn2"]
        )
        s = str(vr)
        self.assertIn("2 warnings", s)

    def test_str_failed(self):
        vr = ValidationResult(
            can_proceed=False, error_message="Something went wrong"
        )
        s = str(vr)
        self.assertIn("Validation failed", s)
        self.assertIn("Something went wrong", s)

    def test_str_failed_with_conflicts(self):
        conflicts = [
            Conflict(
                conflict_type=ConflictType.FILE_MISSING,
                path=f"/file{i}.txt",
                description=f"missing {i}",
            )
            for i in range(5)
        ]
        vr = ValidationResult(
            can_proceed=False,
            error_message="Conflicts found",
            conflicts=conflicts,
        )
        s = str(vr)
        self.assertIn("Conflicts: 5", s)
        # Shows first 3
        self.assertIn("/file0.txt", s)
        self.assertIn("/file1.txt", s)
        self.assertIn("/file2.txt", s)
        # And "more" indicator
        self.assertIn("and 2 more", s)


class TestRollbackResult(unittest.TestCase):
    """Test RollbackResult dataclass."""

    def test_bool_true(self):
        rr = RollbackResult(success=True)
        self.assertTrue(bool(rr))

    def test_bool_false(self):
        rr = RollbackResult(success=False)
        self.assertFalse(bool(rr))

    def test_str_success(self):
        rr = RollbackResult(success=True, operations_rolled_back=3)
        s = str(rr)
        self.assertIn("Rollback successful", s)
        self.assertIn("3 operations", s)

    def test_str_failure(self):
        rr = RollbackResult(
            success=False,
            operations_rolled_back=1,
            operations_failed=2,
            errors=[(1, "err1"), (2, "err2"), (3, "err3"), (4, "err4")],
        )
        s = str(rr)
        self.assertIn("Rollback failed", s)
        self.assertIn("1 succeeded", s)
        self.assertIn("2 failed", s)
        self.assertIn("err1", s)
        self.assertIn("and 1 more errors", s)

    def test_str_with_warnings(self):
        rr = RollbackResult(
            success=True,
            operations_rolled_back=1,
            warnings=["warn1"],
        )
        s = str(rr)
        self.assertIn("Warnings: 1", s)


if __name__ == "__main__":
    unittest.main()
