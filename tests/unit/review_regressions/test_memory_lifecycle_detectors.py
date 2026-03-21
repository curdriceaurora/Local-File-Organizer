"""Unit tests for memory-lifecycle AST detectors (issue #803)."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from file_organizer.review_regressions.memory_lifecycle import (
    MEMORY_LIFECYCLE_DETECTORS,
    AbsoluteRSSInBatchFeedbackDetector,
    EagerBufferPoolAllocationDetector,
    LegacyAcquireReleaseWithoutConsumeDetector,
    PooledBufferOwnershipViaLengthDetector,
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
