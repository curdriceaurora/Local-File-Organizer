"""Unit tests for memory-lifecycle AST detectors (issue #803)."""

from __future__ import annotations

from pathlib import Path

from file_organizer.review_regressions.memory_lifecycle import (
    MEMORY_LIFECYCLE_DETECTORS,
    AbsoluteRSSInBatchFeedbackDetector,
    EagerBufferPoolAllocationDetector,
    LegacyAcquireReleaseWithoutConsumeDetector,
    PooledBufferOwnershipViaLengthDetector,
)


def _fixture_root() -> Path:
    return (
        Path(__file__).resolve().parents[2] / "fixtures" / "review_regressions" / "memory_lifecycle"
    ).resolve()


# ---------------------------------------------------------------------------
# Detector 1: POOLED_BUFFER_OWNERSHIP_VIA_LENGTH
# ---------------------------------------------------------------------------


def test_pooled_buffer_ownership_via_length_flags_len_in_pool_context() -> None:
    detector = PooledBufferOwnershipViaLengthDetector()

    findings = detector.find_violations(_fixture_root())

    positive_findings = [f for f in findings if "buffer_pool_len_positive" in f.path]
    assert positive_findings, "Expected at least one finding in the positive fixture"
    assert all(f.rule_id == "pooled-buffer-ownership-via-length" for f in positive_findings)
    messages = [f.message for f in positive_findings]
    assert any("len(" in m for m in messages)
    assert any("track ownership explicitly" in m for m in messages)


def test_pooled_buffer_ownership_via_length_skips_non_pool_context() -> None:
    detector = PooledBufferOwnershipViaLengthDetector()
    root = _fixture_root()
    safe_path = "src/file_organizer/memory/buffer_pool_len_safe.py"

    assert (root / safe_path).exists(), f"Missing fixture: {safe_path}"

    findings = [f for f in detector.find_violations(root) if f.path == safe_path]
    assert not findings, f"Unexpected findings for {safe_path}: {findings}"


# ---------------------------------------------------------------------------
# Detector 2: EAGER_BUFFER_POOL_ALLOCATION
# ---------------------------------------------------------------------------


def test_eager_buffer_pool_allocation_flags_init_instantiation() -> None:
    detector = EagerBufferPoolAllocationDetector()

    findings = detector.find_violations(_fixture_root())

    positive_findings = [f for f in findings if "eager_pool_positive" in f.path]
    assert positive_findings, "Expected at least one finding in the positive fixture"
    assert all(f.rule_id == "eager-buffer-pool-allocation" for f in positive_findings)
    assert all(
        "BufferPool() should not be instantiated eagerly" in f.message for f in positive_findings
    )


def test_eager_buffer_pool_allocation_skips_deferred_init() -> None:
    detector = EagerBufferPoolAllocationDetector()
    root = _fixture_root()
    safe_path = "src/file_organizer/memory/eager_pool_safe.py"

    assert (root / safe_path).exists(), f"Missing fixture: {safe_path}"

    findings = [f for f in detector.find_violations(root) if f.path == safe_path]
    assert not findings, f"Unexpected findings for {safe_path}: {findings}"


# ---------------------------------------------------------------------------
# Detector 3: ABSOLUTE_RSS_IN_BATCH_FEEDBACK
# ---------------------------------------------------------------------------


def test_absolute_rss_in_batch_feedback_flags_non_delta_rss() -> None:
    detector = AbsoluteRSSInBatchFeedbackDetector()

    findings = detector.find_violations(_fixture_root())

    positive_findings = [f for f in findings if "absolute_rss_positive" in f.path]
    assert positive_findings, "Expected at least one finding in the positive fixture"
    assert all(f.rule_id == "absolute-rss-in-batch-feedback" for f in positive_findings)
    assert all("rss - baseline_rss" in f.message for f in positive_findings)


def test_absolute_rss_in_batch_feedback_skips_delta_rss() -> None:
    detector = AbsoluteRSSInBatchFeedbackDetector()
    root = _fixture_root()
    safe_path = "src/file_organizer/memory/absolute_rss_safe.py"

    assert (root / safe_path).exists(), f"Missing fixture: {safe_path}"

    findings = [f for f in detector.find_violations(root) if f.path == safe_path]
    assert not findings, f"Unexpected findings for {safe_path}: {findings}"


# ---------------------------------------------------------------------------
# Detector 4: LEGACY_ACQUIRE_RELEASE_WITHOUT_CONSUME
# ---------------------------------------------------------------------------


def test_legacy_acquire_release_without_consume_flags_noop_pair() -> None:
    detector = LegacyAcquireReleaseWithoutConsumeDetector()

    findings = detector.find_violations(_fixture_root())

    positive_findings = [f for f in findings if "acquire_release_no_consume_positive" in f.path]
    assert positive_findings, "Expected at least one finding in the positive fixture"
    assert all(f.rule_id == "legacy-acquire-release-without-consume" for f in positive_findings)
    assert all("no-op" in f.message for f in positive_findings)


def test_legacy_acquire_release_without_consume_skips_buffer_with_use() -> None:
    detector = LegacyAcquireReleaseWithoutConsumeDetector()
    root = _fixture_root()
    safe_path = "src/file_organizer/memory/acquire_release_safe.py"

    assert (root / safe_path).exists(), f"Missing fixture: {safe_path}"

    findings = [f for f in detector.find_violations(root) if f.path == safe_path]
    assert not findings, f"Unexpected findings for {safe_path}: {findings}"


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
