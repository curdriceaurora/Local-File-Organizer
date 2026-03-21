"""Unit tests for memory-lifecycle AST detectors (issue #803)."""

from __future__ import annotations

import ast
from pathlib import Path
from textwrap import dedent

import pytest

from file_organizer.review_regressions.memory_lifecycle import (
    MEMORY_LIFECYCLE_DETECTORS,
    AbsoluteRSSInBatchFeedbackDetector,
    EagerBufferPoolAllocationDetector,
    LegacyAcquireReleaseWithoutConsumeDetector,
    PooledBufferOwnershipViaLengthDetector,
    _find_acquire_release_no_consume,
    _has_subtraction_ancestor,
    _is_adjust_feedback_argument,
    _is_baseline_assignment,
    _is_buffer_like_name,
    _is_buffer_pool_call,
    _is_buffer_size_reference,
    _is_len_call_on_name,
    _is_rss_access,
    _is_structural_buffer_size_check,
)


@pytest.fixture(scope="session")
def fixture_root() -> Path:
    """Return the canonical fixture root for memory-lifecycle detector tests."""
    return (
        Path(__file__).resolve().parents[2] / "fixtures" / "review_regressions" / "memory_lifecycle"
    ).resolve()


def _write_fixture_module(root: Path, relative_path: str, source: str) -> Path:
    """Write a synthetic module under *root* and return the created path."""
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dedent(source), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Detector 1: POOLED_BUFFER_OWNERSHIP_VIA_LENGTH
# ---------------------------------------------------------------------------


def test_pooled_buffer_ownership_via_length_flags_len_in_pool_context(
    fixture_root: Path,
) -> None:
    detector = PooledBufferOwnershipViaLengthDetector()

    findings = detector.find_violations(fixture_root)

    positive_findings = [f for f in findings if "buffer_pool_len_positive" in f.path]
    assert positive_findings, "Expected at least one finding in the positive fixture"
    assert all(f.rule_id == "pooled-buffer-ownership-via-length" for f in positive_findings)
    messages = [f.message for f in positive_findings]
    assert any("len(" in m for m in messages)
    assert any("track ownership explicitly" in m for m in messages)


def test_pooled_buffer_ownership_via_length_skips_non_pool_context(
    fixture_root: Path,
) -> None:
    detector = PooledBufferOwnershipViaLengthDetector()
    safe_path = "src/file_organizer/memory/buffer_pool_len_safe.py"

    assert (fixture_root / safe_path).exists(), f"Missing fixture: {safe_path}"

    findings = [f for f in detector.find_violations(fixture_root) if f.path == safe_path]
    assert not findings, f"Unexpected findings for {safe_path}: {findings}"


def test_pooled_buffer_ownership_via_length_skips_non_buffer_names(tmp_path: Path) -> None:
    detector = PooledBufferOwnershipViaLengthDetector()
    _write_fixture_module(
        tmp_path,
        "src/file_organizer/memory/non_buffer_len_safe.py",
        """
        class BufferPool:
            def metrics(self, data: bytes) -> int:
                return len(data)
        """,
    )

    findings = detector.find_violations(tmp_path)
    assert not findings


def test_pooled_buffer_ownership_via_length_skips_structural_size_checks(tmp_path: Path) -> None:
    detector = PooledBufferOwnershipViaLengthDetector()
    _write_fixture_module(
        tmp_path,
        "src/file_organizer/memory/structural_size_safe.py",
        """
        class BufferPool:
            def __init__(self) -> None:
                self._buffer_size = 64

            def release(self, buffer: bytearray) -> bool:
                return len(buffer) == self._buffer_size
        """,
    )

    findings = detector.find_violations(tmp_path)
    assert not findings


# ---------------------------------------------------------------------------
# Detector 2: EAGER_BUFFER_POOL_ALLOCATION
# ---------------------------------------------------------------------------


def test_eager_buffer_pool_allocation_flags_init_instantiation(fixture_root: Path) -> None:
    detector = EagerBufferPoolAllocationDetector()

    findings = detector.find_violations(fixture_root)

    positive_findings = [f for f in findings if "eager_pool_positive" in f.path]
    assert positive_findings, "Expected at least one finding in the positive fixture"
    assert all(f.rule_id == "eager-buffer-pool-allocation" for f in positive_findings)
    assert all(
        "BufferPool() should not be instantiated eagerly" in f.message for f in positive_findings
    )


def test_eager_buffer_pool_allocation_skips_deferred_init(fixture_root: Path) -> None:
    detector = EagerBufferPoolAllocationDetector()
    safe_path = "src/file_organizer/memory/eager_pool_safe.py"

    assert (fixture_root / safe_path).exists(), f"Missing fixture: {safe_path}"

    findings = [f for f in detector.find_violations(fixture_root) if f.path == safe_path]
    assert not findings, f"Unexpected findings for {safe_path}: {findings}"


def test_eager_buffer_pool_allocation_flags_expression_calls_in_init(tmp_path: Path) -> None:
    detector = EagerBufferPoolAllocationDetector()
    _write_fixture_module(
        tmp_path,
        "src/file_organizer/memory/eager_pool_expression_positive.py",
        """
        class BufferPool:
            pass

        class Owner:
            def __init__(self) -> None:
                self._pools = []
                self._pools.append(BufferPool())
        """,
    )

    findings = detector.find_violations(tmp_path)
    assert findings
    assert all(f.rule_id == "eager-buffer-pool-allocation" for f in findings)


# ---------------------------------------------------------------------------
# Detector 3: ABSOLUTE_RSS_IN_BATCH_FEEDBACK
# ---------------------------------------------------------------------------


def test_absolute_rss_in_batch_feedback_flags_non_delta_rss(fixture_root: Path) -> None:
    detector = AbsoluteRSSInBatchFeedbackDetector()

    findings = detector.find_violations(fixture_root)

    positive_findings = [f for f in findings if "absolute_rss_positive" in f.path]
    assert positive_findings, "Expected at least one finding in the positive fixture"
    assert all(f.rule_id == "absolute-rss-in-batch-feedback" for f in positive_findings)
    assert all("rss - baseline_rss" in f.message for f in positive_findings)


def test_absolute_rss_in_batch_feedback_skips_delta_rss(fixture_root: Path) -> None:
    detector = AbsoluteRSSInBatchFeedbackDetector()
    safe_path = "src/file_organizer/memory/absolute_rss_safe.py"

    assert (fixture_root / safe_path).exists(), f"Missing fixture: {safe_path}"

    findings = [f for f in detector.find_violations(fixture_root) if f.path == safe_path]
    assert not findings, f"Unexpected findings for {safe_path}: {findings}"


def test_absolute_rss_in_batch_feedback_flags_direct_feedback_argument(tmp_path: Path) -> None:
    detector = AbsoluteRSSInBatchFeedbackDetector()
    _write_fixture_module(
        tmp_path,
        "src/file_organizer/memory/direct_feedback_positive.py",
        """
        def tune(process, sizer):
            sizer.adjust_from_feedback(process.memory_info().rss)
        """,
    )

    findings = detector.find_violations(tmp_path)
    assert findings
    assert all(f.rule_id == "absolute-rss-in-batch-feedback" for f in findings)


# ---------------------------------------------------------------------------
# Detector 4: LEGACY_ACQUIRE_RELEASE_WITHOUT_CONSUME
# ---------------------------------------------------------------------------


def test_legacy_acquire_release_without_consume_flags_noop_pair(fixture_root: Path) -> None:
    detector = LegacyAcquireReleaseWithoutConsumeDetector()

    findings = detector.find_violations(fixture_root)

    positive_findings = [f for f in findings if "acquire_release_no_consume_positive" in f.path]
    assert positive_findings, "Expected at least one finding in the positive fixture"
    assert all(f.rule_id == "legacy-acquire-release-without-consume" for f in positive_findings)
    assert all("no-op" in f.message for f in positive_findings)


def test_legacy_acquire_release_without_consume_skips_buffer_with_use(
    fixture_root: Path,
) -> None:
    detector = LegacyAcquireReleaseWithoutConsumeDetector()
    safe_path = "src/file_organizer/memory/acquire_release_safe.py"

    assert (fixture_root / safe_path).exists(), f"Missing fixture: {safe_path}"

    findings = [f for f in detector.find_violations(fixture_root) if f.path == safe_path]
    assert not findings, f"Unexpected findings for {safe_path}: {findings}"


def test_legacy_acquire_release_without_consume_ignores_string_literal_mentions(
    tmp_path: Path,
) -> None:
    detector = LegacyAcquireReleaseWithoutConsumeDetector()
    _write_fixture_module(
        tmp_path,
        "src/file_organizer/memory/no_consume_string_positive.py",
        """
        def legacy(pool):
            buf = pool.acquire(10)
            print("buf acquired")
            pool.release(buf)
        """,
    )

    findings = detector.find_violations(tmp_path)
    assert findings
    assert all(f.rule_id == "legacy-acquire-release-without-consume" for f in findings)


def test_legacy_acquire_release_without_consume_ignores_unrelated_attribute_name_collisions(
    tmp_path: Path,
) -> None:
    """An unrelated ``x.buf`` attribute access must not consume pending ``buf``."""
    detector = LegacyAcquireReleaseWithoutConsumeDetector()
    _write_fixture_module(
        tmp_path,
        "src/file_organizer/memory/attribute_collision_positive.py",
        """
        def legacy(pool, x):
            buf = pool.acquire(10)
            x.buf = 0
            pool.release(buf)
        """,
    )

    findings = detector.find_violations(tmp_path)
    assert findings
    assert all(f.rule_id == "legacy-acquire-release-without-consume" for f in findings)


# ---------------------------------------------------------------------------
# Pack-level contract
# ---------------------------------------------------------------------------


def test_memory_lifecycle_detector_pack_exports_all_four_detectors() -> None:
    ids = [d.detector_id for d in MEMORY_LIFECYCLE_DETECTORS]
    assert ids == [
        "memory-lifecycle.pooled-buffer-ownership-via-length",
        "memory-lifecycle.eager-buffer-pool-allocation",
        "memory-lifecycle.absolute-rss-in-batch-feedback",
        "memory-lifecycle.legacy-acquire-release-without-consume",
    ]


# ── T10 predicate negative-case tests (issue #930) ───────────────────────────


def _ml_parents(src: str) -> tuple[ast.AST, dict[ast.AST, ast.AST]]:
    tree = ast.parse(src)
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return tree, parents


def test_is_len_call_on_name_returns_none_for_non_call_node() -> None:
    node = ast.parse("x").body[0].value
    assert not _is_len_call_on_name(node)


def test_is_len_call_on_name_returns_none_for_other_function_call() -> None:
    node = ast.parse("size(buf)").body[0].value
    assert not _is_len_call_on_name(node)


def test_is_buffer_pool_call_returns_false_for_non_call_node() -> None:
    node = ast.parse("BufferPool").body[0].value
    assert not _is_buffer_pool_call(node)


def test_is_buffer_pool_call_returns_false_for_unrelated_call() -> None:
    node = ast.parse("OtherPool()").body[0].value
    assert not _is_buffer_pool_call(node)


def test_is_buffer_like_name_returns_false_for_unrelated_name() -> None:
    assert not _is_buffer_like_name("chunk_data")


def test_is_buffer_size_reference_returns_false_for_unrelated_name() -> None:
    node = ast.parse("chunk_size").body[0].value
    assert not _is_buffer_size_reference(node)


def test_is_buffer_size_reference_returns_false_for_non_name_non_attr() -> None:
    node = ast.parse("42").body[0].value
    assert not _is_buffer_size_reference(node)


def test_is_structural_buffer_size_check_returns_false_when_parent_is_not_compare() -> None:
    src = "len(buf)"
    tree, parents = _ml_parents(src)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert not _is_structural_buffer_size_check(call, parents)


def test_has_subtraction_ancestor_returns_false_when_no_subtraction() -> None:
    src = "x + len(buf)"
    tree, parents = _ml_parents(src)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert not _has_subtraction_ancestor(call, parents)


def test_is_rss_access_returns_false_for_non_rss_attribute() -> None:
    node = ast.parse("proc.memory_info().vms").body[0].value
    assert not _is_rss_access(node)


def test_is_rss_access_returns_false_for_plain_name() -> None:
    node = ast.parse("rss").body[0].value
    assert not _is_rss_access(node)


def test_is_baseline_assignment_returns_false_when_no_baseline_in_target() -> None:
    src = "x = proc.memory_info().rss"
    tree, parents = _ml_parents(src)
    rss_node = next(n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "rss")
    assert not _is_baseline_assignment(rss_node, parents)


def test_is_adjust_feedback_argument_returns_false_when_passed_to_other_function() -> None:
    src = "other_func(proc.memory_info().rss)"
    tree, parents = _ml_parents(src)
    rss_node = next(n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "rss")
    assert not _is_adjust_feedback_argument(rss_node, parents)


def test_find_acquire_release_no_consume_returns_empty_when_buffer_is_consumed() -> None:
    src = dedent("""\
        def f():
            buf = pool.acquire(1024)
            process(buf)
            pool.release(buf)
    """)
    tree = ast.parse(src)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    assert not _find_acquire_release_no_consume(func.body)
