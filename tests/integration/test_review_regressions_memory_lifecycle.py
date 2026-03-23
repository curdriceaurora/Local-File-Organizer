"""Integration tests for the memory-lifecycle review-regression detector pack."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from file_organizer.review_regressions.memory_lifecycle import (
    MEMORY_LIFECYCLE_DETECTORS,
    AbsoluteRSSInBatchFeedbackDetector,
    EagerBufferPoolAllocationDetector,
    LegacyAcquireReleaseWithoutConsumeDetector,
    PooledBufferOwnershipViaLengthDetector,
    _has_subtraction_ancestor,
    _is_adjust_feedback_argument,
    _is_baseline_assignment,
    _is_buffer_like_name,
    _is_buffer_pool_call,
    _is_buffer_size_reference,
    _is_len_call_on_name,
    _is_rss_access,
    _is_structural_buffer_size_check,
    _parent_map,
)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Helper: parse a snippet and build a parent map
# ---------------------------------------------------------------------------


def _parse_and_map(src: str) -> tuple[ast.Module, dict[ast.AST, ast.AST]]:
    tree = ast.parse(src)
    parents = _parent_map(tree)
    return tree, parents


def _first_node_of(tree: ast.AST, node_type: type) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, node_type):
            return node
    raise AssertionError(f"No {node_type.__name__} found in tree")


# ---------------------------------------------------------------------------
# _is_len_call_on_name
# ---------------------------------------------------------------------------


class TestIsLenCallOnName:
    def test_len_of_name_returns_name(self) -> None:
        src = "len(buf)"
        tree = ast.parse(src, mode="eval")
        call = tree.body  # type: ignore[attr-defined]
        assert _is_len_call_on_name(call) == "buf"

    def test_len_of_attribute_returns_none(self) -> None:
        src = "len(obj.buf)"
        tree = ast.parse(src, mode="eval")
        call = tree.body  # type: ignore[attr-defined]
        assert _is_len_call_on_name(call) is None

    def test_non_call_returns_none(self) -> None:
        src = "x"
        tree = ast.parse(src, mode="eval")
        name_node = tree.body  # type: ignore[attr-defined]
        assert _is_len_call_on_name(name_node) is None

    def test_other_builtin_returns_none(self) -> None:
        src = "str(buf)"
        tree = ast.parse(src, mode="eval")
        call = tree.body  # type: ignore[attr-defined]
        assert _is_len_call_on_name(call) is None

    def test_len_with_keyword_arg_returns_none(self) -> None:
        # len() does not accept keyword args, but we test our guard
        fake_call = ast.Call(
            func=ast.Name(id="len", ctx=ast.Load()),
            args=[ast.Name(id="buf", ctx=ast.Load())],
            keywords=[ast.keyword(arg="k", value=ast.Constant(value=1))],
        )
        assert _is_len_call_on_name(fake_call) is None


# ---------------------------------------------------------------------------
# _is_buffer_pool_call
# ---------------------------------------------------------------------------


class TestIsBufferPoolCall:
    def test_bare_bufferpool_call(self) -> None:
        src = "BufferPool()"
        tree = ast.parse(src, mode="eval")
        assert _is_buffer_pool_call(tree.body) is True  # type: ignore[attr-defined]

    def test_qualified_bufferpool_call(self) -> None:
        src = "pools.BufferPool()"
        tree = ast.parse(src, mode="eval")
        assert _is_buffer_pool_call(tree.body) is True  # type: ignore[attr-defined]

    def test_other_call_returns_false(self) -> None:
        src = "OtherPool()"
        tree = ast.parse(src, mode="eval")
        assert _is_buffer_pool_call(tree.body) is False  # type: ignore[attr-defined]

    def test_non_call_node_returns_false(self) -> None:
        src = "x"
        tree = ast.parse(src, mode="eval")
        assert _is_buffer_pool_call(tree.body) is False  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _is_buffer_like_name
# ---------------------------------------------------------------------------


class TestIsBufferLikeName:
    def test_buf_prefix(self) -> None:
        assert _is_buffer_like_name("buf") is True

    def test_buffer_substring(self) -> None:
        assert _is_buffer_like_name("write_buffer") is True

    def test_upper_case_buffer(self) -> None:
        assert _is_buffer_like_name("BUFFER_DATA") is True

    def test_unrelated_name_returns_false(self) -> None:
        assert _is_buffer_like_name("chunk") is False

    def test_empty_string_returns_false(self) -> None:
        assert _is_buffer_like_name("") is False


# ---------------------------------------------------------------------------
# _is_buffer_size_reference
# ---------------------------------------------------------------------------


class TestIsBufferSizeReference:
    def test_name_with_buffer_size(self) -> None:
        node = ast.Name(id="buffer_size", ctx=ast.Load())
        assert _is_buffer_size_reference(node) is True

    def test_attribute_with_buffer_size(self) -> None:
        node = ast.Attribute(
            value=ast.Name(id="self", ctx=ast.Load()),
            attr="buffer_size",
            ctx=ast.Load(),
        )
        assert _is_buffer_size_reference(node) is True

    def test_unrelated_name_returns_false(self) -> None:
        node = ast.Name(id="chunk_size", ctx=ast.Load())
        assert _is_buffer_size_reference(node) is False

    def test_constant_returns_false(self) -> None:
        node = ast.Constant(value=42)
        assert _is_buffer_size_reference(node) is False


# ---------------------------------------------------------------------------
# _is_structural_buffer_size_check
# ---------------------------------------------------------------------------


class TestIsStructuralBufferSizeCheck:
    def test_len_buffer_eq_buffer_size_is_structural(self) -> None:
        src = "len(buf) == buffer_size"
        tree = ast.parse(src, mode="eval")
        parents = _parent_map(tree)
        # The len(buf) Call is the left side of the Compare
        compare = tree.body  # type: ignore[attr-defined]
        len_call = compare.left
        assert _is_structural_buffer_size_check(len_call, parents) is True

    def test_len_buffer_noteq_buffer_size_is_structural(self) -> None:
        src = "len(buf) != buffer_size"
        tree = ast.parse(src, mode="eval")
        parents = _parent_map(tree)
        compare = tree.body  # type: ignore[attr-defined]
        len_call = compare.left
        assert _is_structural_buffer_size_check(len_call, parents) is True

    def test_len_buffer_gt_buffer_size_is_not_structural(self) -> None:
        src = "len(buf) > buffer_size"
        tree = ast.parse(src, mode="eval")
        parents = _parent_map(tree)
        compare = tree.body  # type: ignore[attr-defined]
        len_call = compare.left
        assert _is_structural_buffer_size_check(len_call, parents) is False

    def test_bare_len_call_not_in_compare_returns_false(self) -> None:
        src = "x = len(buf)\n"
        tree, parents = _parse_and_map(src)
        call = _first_node_of(tree, ast.Call)
        assert _is_structural_buffer_size_check(call, parents) is False


# ---------------------------------------------------------------------------
# _has_subtraction_ancestor
# ---------------------------------------------------------------------------


class TestHasSubtractionAncestor:
    def test_inside_subtraction_returns_true(self) -> None:
        src = "x = rss - baseline_rss\n"
        tree, parents = _parse_and_map(src)
        # Find the 'rss' Name node on the right side
        names = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "rss"]
        assert len(names) == 1
        assert _has_subtraction_ancestor(names[0], parents) is True

    def test_simple_assignment_no_subtraction_returns_false(self) -> None:
        src = "x = rss\n"
        tree, parents = _parse_and_map(src)
        names = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "rss"]
        assert _has_subtraction_ancestor(names[0], parents) is False

    def test_addition_is_not_subtraction(self) -> None:
        src = "x = rss + offset\n"
        tree, parents = _parse_and_map(src)
        names = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "rss"]
        assert _has_subtraction_ancestor(names[0], parents) is False


# ---------------------------------------------------------------------------
# _is_rss_access
# ---------------------------------------------------------------------------


class TestIsRssAccess:
    def test_memory_info_rss_returns_true(self) -> None:
        src = "proc.memory_info().rss"
        tree = ast.parse(src, mode="eval")
        attr = tree.body  # type: ignore[attr-defined]
        assert _is_rss_access(attr) is True

    def test_direct_rss_attr_without_call_returns_false(self) -> None:
        src = "proc.rss"
        tree = ast.parse(src, mode="eval")
        attr = tree.body  # type: ignore[attr-defined]
        assert _is_rss_access(attr) is False

    def test_other_attr_on_call_returns_false(self) -> None:
        src = "proc.memory_info().vms"
        tree = ast.parse(src, mode="eval")
        attr = tree.body  # type: ignore[attr-defined]
        assert _is_rss_access(attr) is False

    def test_name_node_returns_false(self) -> None:
        node = ast.Name(id="rss", ctx=ast.Load())
        assert _is_rss_access(node) is False


# ---------------------------------------------------------------------------
# _is_baseline_assignment
# ---------------------------------------------------------------------------


class TestIsBaselineAssignment:
    def test_assigned_to_baseline_variable_returns_true(self) -> None:
        src = "baseline_rss = proc.memory_info().rss\n"
        tree, parents = _parse_and_map(src)
        rss_attr = next(
            n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "rss"
        )
        assert _is_baseline_assignment(rss_attr, parents) is True

    def test_assigned_to_non_baseline_variable_returns_false(self) -> None:
        src = "current_rss = proc.memory_info().rss\n"
        tree, parents = _parse_and_map(src)
        rss_attr = next(
            n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "rss"
        )
        assert _is_baseline_assignment(rss_attr, parents) is False


# ---------------------------------------------------------------------------
# _is_adjust_feedback_argument
# ---------------------------------------------------------------------------


class TestIsAdjustFeedbackArgument:
    def test_direct_call_returns_true(self) -> None:
        src = "adjust_from_feedback(proc.memory_info().rss)\n"
        tree, parents = _parse_and_map(src)
        rss_attr = next(
            n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "rss"
        )
        assert _is_adjust_feedback_argument(rss_attr, parents) is True

    def test_method_call_returns_true(self) -> None:
        src = "self.adjust_from_feedback(proc.memory_info().rss)\n"
        tree, parents = _parse_and_map(src)
        rss_attr = next(
            n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "rss"
        )
        assert _is_adjust_feedback_argument(rss_attr, parents) is True

    def test_other_call_returns_false(self) -> None:
        src = "record(proc.memory_info().rss)\n"
        tree, parents = _parse_and_map(src)
        rss_attr = next(
            n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "rss"
        )
        assert _is_adjust_feedback_argument(rss_attr, parents) is False


# ---------------------------------------------------------------------------
# PooledBufferOwnershipViaLengthDetector
# ---------------------------------------------------------------------------


class TestPooledBufferOwnershipViaLengthDetector:
    @pytest.fixture()
    def detector(self) -> PooledBufferOwnershipViaLengthDetector:
        return PooledBufferOwnershipViaLengthDetector()

    def test_empty_dir_no_violations(
        self, detector: PooledBufferOwnershipViaLengthDetector, tmp_path: Path
    ) -> None:
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_len_buf_in_acquire_produces_violation(
        self, detector: PooledBufferOwnershipViaLengthDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "pool.py").write_text(
            "def acquire(self, buf):\n    if len(buf) > 0:\n        return buf\n"
        )
        result = detector.find_violations(tmp_path)
        assert len(result) == 1
        assert result[0].rule_id == "pooled-buffer-ownership-via-length"
        assert "len(buf)" in result[0].message

    def test_len_buf_inside_bufferpool_class_produces_violation(
        self, detector: PooledBufferOwnershipViaLengthDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "pool.py").write_text(
            "class BufferPool:\n    def some_method(self, buf):\n        x = len(buf)\n"
        )
        result = detector.find_violations(tmp_path)
        assert len(result) == 1

    def test_structural_size_check_is_not_flagged(
        self, detector: PooledBufferOwnershipViaLengthDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "pool.py").write_text(
            "def acquire(self, buf, buffer_size):\n    if len(buf) == buffer_size:\n        pass\n"
        )
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_len_buf_outside_pool_context_not_flagged(
        self, detector: PooledBufferOwnershipViaLengthDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "utils.py").write_text("def helper(buf):\n    return len(buf)\n")
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_len_non_buffer_name_in_pool_not_flagged(
        self, detector: PooledBufferOwnershipViaLengthDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "pool.py").write_text("def acquire(self, items):\n    x = len(items)\n")
        result = detector.find_violations(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# EagerBufferPoolAllocationDetector
# ---------------------------------------------------------------------------


class TestEagerBufferPoolAllocationDetector:
    @pytest.fixture()
    def detector(self) -> EagerBufferPoolAllocationDetector:
        return EagerBufferPoolAllocationDetector()

    def test_empty_dir_no_violations(
        self, detector: EagerBufferPoolAllocationDetector, tmp_path: Path
    ) -> None:
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_bufferpool_in_init_assign_produces_violation(
        self, detector: EagerBufferPoolAllocationDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "service.py").write_text(
            "class MyService:\n    def __init__(self):\n        self.pool = BufferPool()\n"
        )
        result = detector.find_violations(tmp_path)
        assert len(result) == 1
        assert result[0].rule_id == "eager-buffer-pool-allocation"
        assert "BufferPool" in result[0].message

    def test_bufferpool_in_init_annassign_produces_violation(
        self, detector: EagerBufferPoolAllocationDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "service.py").write_text(
            "class MyService:\n"
            "    def __init__(self):\n"
            "        self.pool: BufferPool = BufferPool()\n"
        )
        result = detector.find_violations(tmp_path)
        assert len(result) == 1

    def test_bufferpool_in_regular_method_not_flagged(
        self, detector: EagerBufferPoolAllocationDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "service.py").write_text(
            "class MyService:\n    def setup(self):\n        self.pool = BufferPool()\n"
        )
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_qualified_bufferpool_in_init_produces_violation(
        self, detector: EagerBufferPoolAllocationDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "service.py").write_text(
            "class MyService:\n    def __init__(self):\n        self.pool = pools.BufferPool()\n"
        )
        result = detector.find_violations(tmp_path)
        assert len(result) == 1

    def test_other_class_in_init_not_flagged(
        self, detector: EagerBufferPoolAllocationDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "service.py").write_text(
            "class MyService:\n    def __init__(self):\n        self.other = OtherPool()\n"
        )
        result = detector.find_violations(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# AbsoluteRSSInBatchFeedbackDetector
# ---------------------------------------------------------------------------


class TestAbsoluteRSSInBatchFeedbackDetector:
    @pytest.fixture()
    def detector(self) -> AbsoluteRSSInBatchFeedbackDetector:
        return AbsoluteRSSInBatchFeedbackDetector()

    def test_empty_dir_no_violations(
        self, detector: AbsoluteRSSInBatchFeedbackDetector, tmp_path: Path
    ) -> None:
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_absolute_rss_assigned_produces_violation(
        self, detector: AbsoluteRSSInBatchFeedbackDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "loop.py").write_text(
            "import psutil\n"
            "proc = psutil.Process()\n"
            "def process_batch(proc):\n"
            "    rss = proc.memory_info().rss\n"
        )
        result = detector.find_violations(tmp_path)
        assert len(result) == 1
        assert result[0].rule_id == "absolute-rss-in-batch-feedback"
        assert "delta" in result[0].message or "absolute" in result[0].message

    def test_rss_in_subtraction_not_flagged(
        self, detector: AbsoluteRSSInBatchFeedbackDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "loop.py").write_text(
            "def process_batch(proc):\n    delta = proc.memory_info().rss - baseline_rss\n"
        )
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_rss_in_baseline_assignment_not_flagged(
        self, detector: AbsoluteRSSInBatchFeedbackDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "loop.py").write_text(
            "def process_batch(proc):\n    baseline_rss = proc.memory_info().rss\n"
        )
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_rss_passed_to_adjust_from_feedback_produces_violation(
        self, detector: AbsoluteRSSInBatchFeedbackDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "loop.py").write_text(
            "def run(proc):\n    adjust_from_feedback(proc.memory_info().rss)\n"
        )
        result = detector.find_violations(tmp_path)
        assert len(result) == 1

    def test_rss_not_in_assignment_or_feedback_not_flagged(
        self, detector: AbsoluteRSSInBatchFeedbackDetector, tmp_path: Path
    ) -> None:
        # RSS accessed as bare expression statement (not assigned, not in feedback call)
        (tmp_path / "loop.py").write_text("def run(proc):\n    proc.memory_info().rss\n")
        result = detector.find_violations(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# LegacyAcquireReleaseWithoutConsumeDetector
# ---------------------------------------------------------------------------


class TestLegacyAcquireReleaseWithoutConsumeDetector:
    @pytest.fixture()
    def detector(self) -> LegacyAcquireReleaseWithoutConsumeDetector:
        return LegacyAcquireReleaseWithoutConsumeDetector()

    def test_empty_dir_no_violations(
        self, detector: LegacyAcquireReleaseWithoutConsumeDetector, tmp_path: Path
    ) -> None:
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_acquire_then_release_no_consume_produces_violation(
        self, detector: LegacyAcquireReleaseWithoutConsumeDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "legacy.py").write_text(
            "def flush(pool):\n    buf = pool.acquire(1024)\n    pool.release(buf)\n"
        )
        result = detector.find_violations(tmp_path)
        assert len(result) == 1
        assert result[0].rule_id == "legacy-acquire-release-without-consume"
        assert "no-op" in result[0].message or "legacy" in result[0].message

    def test_acquire_with_consume_before_release_not_flagged(
        self, detector: LegacyAcquireReleaseWithoutConsumeDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "ok.py").write_text(
            "def process(pool):\n"
            "    buf = pool.acquire(1024)\n"
            "    write(buf)\n"
            "    pool.release(buf)\n"
        )
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_acquire_only_no_release_not_flagged(
        self, detector: LegacyAcquireReleaseWithoutConsumeDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "ok.py").write_text(
            "def process(pool):\n    buf = pool.acquire(1024)\n    return buf\n"
        )
        result = detector.find_violations(tmp_path)
        assert result == []

    def test_violation_includes_line_number(
        self, detector: LegacyAcquireReleaseWithoutConsumeDetector, tmp_path: Path
    ) -> None:
        (tmp_path / "legacy.py").write_text(
            "def flush(pool):\n    buf = pool.acquire(1024)\n    pool.release(buf)\n"
        )
        result = detector.find_violations(tmp_path)
        assert len(result) == 1
        assert result[0].line is not None
        assert result[0].line >= 1


# ---------------------------------------------------------------------------
# MEMORY_LIFECYCLE_DETECTORS tuple
# ---------------------------------------------------------------------------


class TestMemoryLifecycleDetectorsTuple:
    def test_contains_all_four_detectors(self) -> None:
        ids = {d.detector_id for d in MEMORY_LIFECYCLE_DETECTORS}
        assert "memory-lifecycle.pooled-buffer-ownership-via-length" in ids
        assert "memory-lifecycle.eager-buffer-pool-allocation" in ids
        assert "memory-lifecycle.absolute-rss-in-batch-feedback" in ids
        assert "memory-lifecycle.legacy-acquire-release-without-consume" in ids

    def test_all_detectors_implement_find_violations(self) -> None:
        for detector in MEMORY_LIFECYCLE_DETECTORS:
            assert callable(getattr(detector, "find_violations", None))

    def test_all_detectors_have_detector_id(self) -> None:
        for detector in MEMORY_LIFECYCLE_DETECTORS:
            assert isinstance(detector.detector_id, str)
            assert len(detector.detector_id) > 0

    def test_all_detectors_have_rule_class(self) -> None:
        for detector in MEMORY_LIFECYCLE_DETECTORS:
            assert detector.rule_class == "memory-lifecycle"
