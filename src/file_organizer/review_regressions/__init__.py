"""Framework for detector-based review-regression audits."""

from file_organizer.review_regressions.correctness import (
    CORRECTNESS_DETECTORS,
    ActiveModelPrimitiveStoreDetector,
    StageContextValidationBypassDetector,
)
from file_organizer.review_regressions.framework import (
    AuditReport,
    DetectorDescriptor,
    ReviewRegressionDetector,
    Violation,
    fingerprint_ast_node,
    iter_python_files,
    parse_python_ast,
    render_report_json,
    run_audit,
)
from file_organizer.review_regressions.memory_lifecycle import (
    MEMORY_LIFECYCLE_DETECTORS,
    AbsoluteRSSInBatchFeedbackDetector,
    EagerBufferPoolAllocationDetector,
    LegacyAcquireReleaseWithoutConsumeDetector,
    PooledBufferOwnershipViaLengthDetector,
)
from file_organizer.review_regressions.security import (
    SECURITY_DETECTORS,
    GuardedContextDirectPathDetector,
    ValidatedPathBypassDetector,
)
from file_organizer.review_regressions.test_quality import (
    TEST_QUALITY_DETECTORS,
    WeakMockCallCountAssertionDetector,
    changed_test_quality_detectors,
)

__all__ = [
    "AuditReport",
    "DetectorDescriptor",
    "ReviewRegressionDetector",
    "Violation",
    "AbsoluteRSSInBatchFeedbackDetector",
    "ActiveModelPrimitiveStoreDetector",
    "CORRECTNESS_DETECTORS",
    "EagerBufferPoolAllocationDetector",
    "GuardedContextDirectPathDetector",
    "LegacyAcquireReleaseWithoutConsumeDetector",
    "MEMORY_LIFECYCLE_DETECTORS",
    "PooledBufferOwnershipViaLengthDetector",
    "TEST_QUALITY_DETECTORS",
    "ValidatedPathBypassDetector",
    "StageContextValidationBypassDetector",
    "SECURITY_DETECTORS",
    "WeakMockCallCountAssertionDetector",
    "changed_test_quality_detectors",
    "fingerprint_ast_node",
    "iter_python_files",
    "parse_python_ast",
    "render_report_json",
    "run_audit",
]
