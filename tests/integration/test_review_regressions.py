"""Integration tests for review regression detectors.

Covers:
  - review_regressions/correctness.py     — detectors
  - review_regressions/memory_lifecycle.py — detectors
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.review_regressions.correctness import (
    CORRECTNESS_DETECTORS,
    ActiveModelPrimitiveStoreDetector,
    StageContextValidationBypassDetector,
    Violation,
    iter_python_files,
    parse_python_ast,
)
from file_organizer.review_regressions.memory_lifecycle import (
    MEMORY_LIFECYCLE_DETECTORS,
    AbsoluteRSSInBatchFeedbackDetector,
    EagerBufferPoolAllocationDetector,
    LegacyAcquireReleaseWithoutConsumeDetector,
    PooledBufferOwnershipViaLengthDetector,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Violation dataclass
# ---------------------------------------------------------------------------


class TestViolation:
    def test_violation_created(self) -> None:
        v = Violation(
            detector_id="test",
            rule_class="TestClass",
            rule_id="T001",
            path="test.py",
            message="test violation",
        )
        assert v.detector_id == "test"
        assert v.rule_id == "T001"

    def test_violation_optional_line(self) -> None:
        v = Violation(
            detector_id="d",
            rule_class="C",
            rule_id="R",
            path="/f.py",
            message="msg",
            line=42,
        )
        assert v.line == 42

    def test_violation_default_line_none(self) -> None:
        v = Violation(
            detector_id="d",
            rule_class="C",
            rule_id="R",
            path="/f.py",
            message="msg",
        )
        assert v.line is None

    def test_violation_fingerprint_basis(self) -> None:
        v = Violation(
            detector_id="d",
            rule_class="C",
            rule_id="R",
            path="/f.py",
            message="msg",
            fingerprint_basis="some_code",
        )
        assert v.fingerprint_basis == "some_code"


# ---------------------------------------------------------------------------
# iter_python_files / parse_python_ast
# ---------------------------------------------------------------------------


class TestIterPythonFiles:
    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        result = list(iter_python_files(tmp_path))
        assert result == []

    def test_finds_py_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")
        result = list(iter_python_files(tmp_path))
        assert len(result) == 2

    def test_ignores_non_py_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.txt").write_text("y = 2")
        result = list(iter_python_files(tmp_path))
        assert len(result) == 1

    def test_recursive_finds_nested(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.py").write_text("z = 3")
        result = list(iter_python_files(tmp_path))
        assert len(result) >= 1

    def test_returns_path_objects(self, tmp_path: Path) -> None:
        (tmp_path / "test.py").write_text("pass")
        result = list(iter_python_files(tmp_path))
        assert all(isinstance(p, Path) for p in result)


class TestParsePythonAST:
    def test_valid_python_returns_tree(self, tmp_path: Path) -> None:
        f = tmp_path / "valid.py"
        f.write_text("x = 1\ny = 2\n")
        tree = parse_python_ast(f)
        assert tree is not None

    def test_invalid_python_returns_none_or_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "invalid.py"
        f.write_text("def foo(\n  # unclosed\n")
        try:
            tree = parse_python_ast(f)
            assert tree is None
        except SyntaxError:
            pass  # Acceptable: implementation may propagate SyntaxError

    def test_empty_file_parses(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        tree = parse_python_ast(f)
        assert tree is not None


# ---------------------------------------------------------------------------
# CORRECTNESS_DETECTORS list
# ---------------------------------------------------------------------------


class TestCorrectnessDetectorsList:
    def test_detectors_not_empty(self) -> None:
        assert len(CORRECTNESS_DETECTORS) > 0

    def test_all_have_find_violations(self) -> None:
        for detector in CORRECTNESS_DETECTORS:
            assert hasattr(detector, "find_violations")


# ---------------------------------------------------------------------------
# ActiveModelPrimitiveStoreDetector
# ---------------------------------------------------------------------------


class TestActiveModelDetector:
    def test_clean_code_no_violations(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.py"
        f.write_text("x = {}\nx['key'] = 'value'\n")
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_find_violations_returns_list(self, tmp_path: Path) -> None:
        detector = ActiveModelPrimitiveStoreDetector()
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_violations_are_violation_objects(self, tmp_path: Path) -> None:
        f = tmp_path / "code.py"
        f.write_text("x = 1\n")
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        for v in violations:
            assert isinstance(v, Violation)

    def test_empty_dir_no_violations(self, tmp_path: Path) -> None:
        detector = ActiveModelPrimitiveStoreDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []


# ---------------------------------------------------------------------------
# StageContextValidationBypassDetector
# ---------------------------------------------------------------------------


class TestStageContextDetector:
    def test_clean_code_no_violations(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.py"
        f.write_text("class MyClass:\n    pass\n")
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_empty_dir_no_violations(self, tmp_path: Path) -> None:
        detector = StageContextValidationBypassDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_find_violations_returns_list(self, tmp_path: Path) -> None:
        detector = StageContextValidationBypassDetector()
        result = detector.find_violations(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# MEMORY_LIFECYCLE_DETECTORS list
# ---------------------------------------------------------------------------


class TestMemoryLifecycleDetectorsList:
    def test_detectors_not_empty(self) -> None:
        assert len(MEMORY_LIFECYCLE_DETECTORS) > 0

    def test_all_have_find_violations(self) -> None:
        for detector in MEMORY_LIFECYCLE_DETECTORS:
            assert hasattr(detector, "find_violations")


# ---------------------------------------------------------------------------
# AbsoluteRSSInBatchFeedbackDetector
# ---------------------------------------------------------------------------


class TestAbsoluteRSSDetector:
    def test_empty_dir_no_violations(self, tmp_path: Path) -> None:
        detector = AbsoluteRSSInBatchFeedbackDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_clean_code_no_violations(self, tmp_path: Path) -> None:
        f = tmp_path / "code.py"
        f.write_text("import psutil\nproc = psutil.Process()\n")
        detector = AbsoluteRSSInBatchFeedbackDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []


# ---------------------------------------------------------------------------
# EagerBufferPoolAllocationDetector
# ---------------------------------------------------------------------------


class TestEagerBufferPoolDetector:
    def test_empty_dir_no_violations(self, tmp_path: Path) -> None:
        detector = EagerBufferPoolAllocationDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_find_violations_returns_list(self, tmp_path: Path) -> None:
        (tmp_path / "code.py").write_text("x = 1\n")
        detector = EagerBufferPoolAllocationDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []


# ---------------------------------------------------------------------------
# LegacyAcquireReleaseWithoutConsumeDetector
# ---------------------------------------------------------------------------


class TestLegacyAcquireDetector:
    def test_empty_dir_no_violations(self, tmp_path: Path) -> None:
        detector = LegacyAcquireReleaseWithoutConsumeDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_clean_acquire_release_pattern(self, tmp_path: Path) -> None:
        code = "pool = BufferPool()\nbuf = pool.acquire()\ndata = bytes(buf)\npool.release(buf)\n"
        (tmp_path / "code.py").write_text(code)
        detector = LegacyAcquireReleaseWithoutConsumeDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []


# ---------------------------------------------------------------------------
# PooledBufferOwnershipViaLengthDetector
# ---------------------------------------------------------------------------


class TestPooledBufferOwnershipDetector:
    def test_empty_dir_no_violations(self, tmp_path: Path) -> None:
        detector = PooledBufferOwnershipViaLengthDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []

    def test_find_violations_returns_list(self, tmp_path: Path) -> None:
        (tmp_path / "code.py").write_text("x = 1\n")
        detector = PooledBufferOwnershipViaLengthDetector()
        violations = detector.find_violations(tmp_path)
        assert violations == []
